"""
Plan-based entitlements — per-(user, resource) monthly counters.

This is the module that turns "5 jobs/month on the free plan" into code.
It's the complement to core.rate_limit:
    - rate_limit.py enforces BURST caps (60 AI calls / minute per user)
      to keep scrapers and stuck loops from DDoSing the backend.
    - entitlements.py enforces PLAN caps (5 jobs / month on free; 50 on
      paid) to keep Anthropic spend bounded per user.

Both apply to every paid AI endpoint. They have independent key
spaces, storage, and semantics; you can exceed the burst limit without
exceeding your monthly cap, and vice versa.

Design decisions (preserved because they'll get questioned later):

1. Postgres, not Redis, for the counter. Billing-adjacent state must
   survive Redis evictions / restarts. The Postgres UPSERT idiom
   (INSERT ... ON CONFLICT ... DO UPDATE SET count = count + 1
   RETURNING count) is atomic and cheap enough at our scale.

2. Anchor the window to user.created_at day-of-month, not the 1st. It
   matches "reset on anniversary of signup" from the spec. Each user
   has their own month boundaries.

3. Short-month clamp. A user signed up on Jan 31 sees their Feb window
   reset on Feb 28/29, not by rolling into Mar 3. That's the intuitive
   behaviour — Python's dateutil handles it if we import it, but we
   don't pull a new dep for one function; see _add_one_month below.

4. paid_grandfathered users are NEVER over quota. consume() still
   writes the row (useful for analytics — "what would this user cost
   on the paid plan?"), but never raises. This is how we make sure
   the developer account can't be locked out by a bug in this module.

5. Refund on AI-call failure. The route wraps the Anthropic call in
   try/except; on failure it calls refund() before re-raising. The
   counter is relative (+1 / -1 via UPSERT), so concurrency is safe.
   A process crash between consume and refund leaks ONE credit.
   Acceptable.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_counter import UsageCounter
from app.models.user import User


Scope = Literal["user", "job"]


@dataclass(frozen=True)
class Resource:
    """One entitled action. Limits are monthly caps per scope.

    free  — limit for plan='free' (the only limit visible to anonymous
            marketing copy).
    paid  — limit for plan='paid'. paid_grandfathered ignores this and
            is treated as unlimited in plan_limit().
    scope — 'user' means one counter per user per month.
            'job' means one counter per (user, job) per month — each
            job gets its own 3/10-drafts allowance so generating an
            outreach on job A doesn't consume job B's allowance.
    """

    free: int
    paid: int
    scope: Scope


# The single source of truth for every entitled resource. Adding a new
# resource here + wiring Depends(entitlement(...)) on the route is all
# it takes to enforce a new cap. GET /billing/status iterates over this
# dict to report usage to the frontend.
#
# Resource key conventions:
#   jobs_created          — counts successful POST /jobs* (any source).
#   company_research      — counts POST /jobs/{id}/company-research (even
#                            if the response is served from cache — see
#                            company_research.py for the why).
#   draft_<kind>          — counts POST /jobs/{id}/ai-outputs/<kind>.
#   cover_letter          — counts POST /jobs/{id}/cover-letters.
#   ai_job_search         — reserved for a future feature. The resource
#                            is registered so its counter column already
#                            exists; there's no route yet.
RESOURCES: dict[str, Resource] = {
    "jobs_created":         Resource(free=5,  paid=50, scope="user"),
    "company_research":     Resource(free=3,  paid=10, scope="user"),
    "draft_outreach":       Resource(free=3,  paid=10, scope="job"),
    "draft_form_response":  Resource(free=3,  paid=10, scope="job"),
    "draft_follow_up":      Resource(free=3,  paid=10, scope="job"),
    "draft_interview_prep": Resource(free=3,  paid=10, scope="job"),
    "cover_letter":         Resource(free=3,  paid=10, scope="job"),
    "ai_job_search":        Resource(free=1,  paid=5,  scope="user"),
    # CV generator is paid-only: free=0 means the quota check fails for
    # free users with the standard 402 response, which the frontend turns
    # into the Upgrade CTA. Paid users get 2/cycle — enough to try again
    # after a disappointing first draft but scarce enough to stay cheap.
    "cv_generation":        Resource(free=0,  paid=2,  scope="user"),
}


def _add_one_month(dt: datetime) -> datetime:
    """Return `dt` + one calendar month, clamped to the last valid day.

    "Clamp" is the important word — if dt is Jan 31 00:00 UTC, the next
    window starts Feb 28 (or Feb 29 in a leap year), not Mar 3. This
    matches how humans reason about monthly anniversaries.

    We don't use dateutil.relativedelta here to avoid the dependency
    for one helper; the stdlib calendar module gives us the last day
    of any (year, month).
    """
    year = dt.year + (1 if dt.month == 12 else 0)
    month = 1 if dt.month == 12 else dt.month + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, last_day)
    return dt.replace(year=year, month=month, day=day)


def current_window(user: User, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return the user's active entitlement window as (start, end).

    Anchor:
        The window's day-of-month anchor is user.created_at.day, and
        the window starts at 00:00 UTC on that anchor day in the
        current-or-previous month (whichever is in the past).

    End:
        window_end = _add_one_month(window_start). Exclusive — counters
        with window_start == W belong to the window [W, _add_one_month(W)).

    Example: user signed up 2026-04-17 14:03 UTC. Today is 2026-06-02.
        anchor_day = 17
        Candidate this month: 2026-06-17 00:00 UTC (in the future).
        → Walk back one month: 2026-05-17 00:00 UTC. This is the start.
        window_end: 2026-06-17 00:00 UTC.

    Edge case: user signed up 2026-01-31. On 2026-02-15, the current
    window is 2026-01-31 → 2026-02-28. On 2026-03-01 the window flips
    to 2026-02-28 → 2026-03-28 (anchor clamped down to a valid day for
    February, then _add_one_month gives a fresh 31 for March).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    created = user.created_at
    if created.tzinfo is None:
        # Legacy rows without timezone info — treat as UTC rather than
        # raising, so a forgotten DB timezone setting doesn't brick
        # every entitlement check.
        created = created.replace(tzinfo=timezone.utc)

    anchor_day = created.day
    # Build the "anchor date this month" in UTC at 00:00. Clamp the day
    # in case this month is shorter than anchor_day (Jan 31 → Feb 28).
    this_month_last = calendar.monthrange(now.year, now.month)[1]
    this_month_anchor = datetime.combine(
        now.date().replace(day=min(anchor_day, this_month_last)),
        time(0, 0),
        tzinfo=timezone.utc,
    )

    if this_month_anchor <= now:
        start = this_month_anchor
    else:
        # Walk one month back. Compute the previous month's anchor
        # with the same short-month clamp.
        prev_year = now.year - (1 if now.month == 1 else 0)
        prev_month = 12 if now.month == 1 else now.month - 1
        prev_month_last = calendar.monthrange(prev_year, prev_month)[1]
        start = datetime(
            prev_year,
            prev_month,
            min(anchor_day, prev_month_last),
            tzinfo=timezone.utc,
        )

    return start, _add_one_month(start)


def plan_limit(user: User, resource: str) -> int | None:
    """Return the cap for this user on this resource, or None for unlimited.

    Unknown resources raise — entitled routes must register their key in
    RESOURCES, and a typo should fail loudly, not silently default to
    free-tier caps.
    """
    if resource not in RESOURCES:
        raise ValueError(f"Unknown resource: {resource!r}")

    if user.plan == "paid_grandfathered":
        return None  # admin override — unlimited

    spec = RESOURCES[resource]
    if user.plan == "paid":
        return spec.paid
    # Default to free for any unexpected plan string. Fail-safe: an
    # unknown plan value shouldn't accidentally unlock paid caps.
    return spec.free


class QuotaExceeded(HTTPException):
    """402 Payment Required with a structured body the frontend can render.

    Why 402 rather than 403:
        403 means "you can't do this ever". 402 means "you can't do this
        without paying" — which is literally the case here. Browsers
        don't treat 402 specially; it's just a status code. The frontend
        API client turns it into an upgrade CTA.
    """

    def __init__(
        self,
        *,
        resource: str,
        limit: int,
        used: int,
        resets_at: datetime,
        upgrade_url: str = "/billing",
    ) -> None:
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "quota_exceeded",
                "resource": resource,
                "limit": limit,
                "used": used,
                "resets_at": resets_at.isoformat(),
                "upgrade_url": upgrade_url,
            },
        )


async def remaining(
    db: AsyncSession,
    user: User,
    resource: str,
    scope_key: UUID | None = None,
) -> int | None:
    """Read-only "how many do I have left?" — None means unlimited.

    Used by GET /billing/status and by GET /jobs/{id} (quota block).
    Does NOT upsert — a user who's never touched a resource has zero
    rows; we compute remaining = limit - 0 = limit.
    """
    limit = plan_limit(user, resource)
    if limit is None:
        return None

    start, _end = current_window(user)

    # Direct SELECT — no write side effect. Reading-by-conflict would
    # need an UPSERT with count+0, which is a write; avoid it.
    from sqlalchemy import select

    q = select(UsageCounter.count).where(
        UsageCounter.user_id == user.id,
        UsageCounter.resource == resource,
        UsageCounter.window_start == start,
    )
    if scope_key is None:
        q = q.where(UsageCounter.scope_key.is_(None))
    else:
        q = q.where(UsageCounter.scope_key == scope_key)

    row = (await db.execute(q)).scalar_one_or_none()
    used = int(row or 0)
    return max(limit - used, 0)


async def consume(
    db: AsyncSession,
    user: User,
    resource: str,
    scope_key: UUID | None = None,
    *,
    upgrade_url: str = "/billing",
) -> int:
    """Increment the counter for (user, resource, scope_key) in the
    current window, and return the new count.

    Raises QuotaExceeded (402) if the increment would put the user over
    their plan limit. paid_grandfathered never raises.

    Commits the row independently of the route's own commit — otherwise
    a failing Anthropic call in the same DB transaction would roll the
    counter back and the user could burn credits without ever being
    charged against them on retry. (Opposite problem to the refund
    path: consume must PERSIST eagerly.)

    Concurrency:
        Postgres serialises concurrent UPSERTs on the unique index.
        Two parallel `consume` calls on the same (user, resource,
        scope, window) row both return monotonically-increasing counts
        — no lost updates.
    """
    if resource not in RESOURCES:
        raise ValueError(f"Unknown resource: {resource!r}")

    start, end = current_window(user)

    stmt = (
        pg_insert(UsageCounter)
        .values(
            user_id=user.id,
            resource=resource,
            scope_key=scope_key,
            window_start=start,
            window_end=end,
            count=1,
        )
        .on_conflict_do_update(
            # This must match the unique constraint name/shape exactly.
            # Using constraint= (by name) rather than index_elements
            # because NULL scope_key + multi-column indexes behave
            # differently across PG versions — constraint lookup is
            # the stable path.
            constraint="uq_usage_counter_user_resource_scope_window",
            set_={"count": UsageCounter.count + 1},
        )
        .returning(UsageCounter.count)
    )

    new_count = int((await db.execute(stmt)).scalar_one())
    await db.commit()

    limit = plan_limit(user, resource)
    if limit is not None and new_count > limit:
        # Over quota. Roll the counter back by one and raise 402.
        # We MUST do this commit-first: if we raised before rolling
        # back, the count would stay incremented and the user would
        # appear to have used more than they did.
        await refund(db, user, resource, scope_key)
        raise QuotaExceeded(
            resource=resource,
            limit=limit,
            used=limit,  # over = they've hit the cap
            resets_at=end,
            upgrade_url=upgrade_url,
        )

    return new_count


async def refund(
    db: AsyncSession,
    user: User,
    resource: str,
    scope_key: UUID | None = None,
) -> None:
    """Decrement the counter by 1, with a floor at 0.

    Called in two situations:
        1. Inside consume() when a consume would exceed the quota — we
           bump then decrement because atomic "check and maybe increment"
           is awkward in Postgres UPSERT.
        2. By a route when the downstream Anthropic call fails, so a
           failed generation doesn't count against the user.

    The floor-at-0 (`GREATEST(count - 1, 0)`) is defensive: concurrent
    refund races or an over-enthusiastic caller shouldn't send the
    counter negative and break the limit check on subsequent consumes.
    """
    start, _end = current_window(user)

    # Floor at zero with GREATEST(count - 1, 0). The previous version
    # used unbounded subtraction "for portability", but this app is
    # Postgres-only and an unbounded refund is exploitable: any path
    # where refund() runs without a matching consume() (cleanup-after-
    # exception double-fire, future bug, deliberate trigger) drives the
    # counter negative and grants the user free credits on subsequent
    # legitimate consumes.
    count_col = UsageCounter.__table__.c.count
    stmt = (
        update(UsageCounter)
        .where(
            UsageCounter.user_id == user.id,
            UsageCounter.resource == resource,
            UsageCounter.window_start == start,
        )
        .values(count=func.greatest(count_col - 1, 0))
    )
    if scope_key is None:
        stmt = stmt.where(UsageCounter.scope_key.is_(None))
    else:
        stmt = stmt.where(UsageCounter.scope_key == scope_key)

    await db.execute(stmt)
    await db.commit()
