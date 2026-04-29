"""Dashboard aggregation endpoints.

Currently exposes only the funnel — the Sankey on the home page. The
endpoint walks every job_status_history row owned by the caller in a
single query, groups by job, and emits one Sankey link per consecutive
(from_status, to_status) pair.

Why aggregate in Python rather than SQL:
    The grouping is naturally per-job and ordered by changed_at. We
    could write this as a window-function query (LAG over partitioned
    by job_id) and a GROUP BY (from, to), but the result set is small
    (one row per transition per user) and the Python form is far
    easier to review for correctness. If the funnel ever spans tens of
    thousands of rows per user, revisit.

Caching:
    Held off for now — even a power user is unlikely to have more than
    a few hundred history rows, and a single GET against the dashboard
    on each load is cheap. If a server-side cache becomes worthwhile
    later, Redis with a 60s TTL keyed on user_id is the obvious shape.
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.job_status_history import JobStatusHistory
from app.models.user import User
from app.schemas.dashboard import FunnelLink, FunnelNode, FunnelOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# Single source of truth for stage labels. Order matters for the
# Sankey layout — Plotly draws nodes left-to-right in the order we
# declare them, so the linear ladder appears horizontally and the
# terminal off-ramps stack to the right.
STAGE_LABELS: dict[str, str] = {
    "saved": "Saved",
    "applied": "Applied",
    "first_interview": "First interview",
    "second_interview": "Second interview",
    "final_interview": "Final interview",
    "offer": "Offer",
    "accepted": "Accepted",
    "rejected": "Rejected",
    "withdrawn": "Withdrawn",
    "ghosted": "Ghosted",
    "declined": "Declined",
}


WindowKey = Literal["all", "90d", "365d"]


def _window_start(window: WindowKey, now: datetime) -> datetime | None:
    """Resolve a friendly window key to an inclusive lower bound.

    "all" returns None — the route uses that to skip the time filter
    entirely so a user with old jobs still sees their full history.
    """
    if window == "90d":
        return now - timedelta(days=90)
    if window == "365d":
        return now - timedelta(days=365)
    return None


@router.get("/funnel", response_model=FunnelOut)
async def funnel(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    window: WindowKey = Query(default="all"),
) -> FunnelOut:
    now = datetime.now(timezone.utc)
    window_start = _window_start(window, now)

    # Pull every history row for this user. We DON'T filter by
    # changed_at on the SQL side because a job's earlier transitions
    # are needed even when the time window cuts mid-journey — see
    # below for how the window is applied.
    stmt = (
        select(JobStatusHistory)
        .where(JobStatusHistory.user_id == user.id)
        .order_by(JobStatusHistory.job_id, JobStatusHistory.changed_at)
    )
    rows = (await db.execute(stmt)).scalars().all()

    # Group rows by job so we can walk each job's timeline in order.
    by_job: dict[UUID, list[JobStatusHistory]] = defaultdict(list)
    for row in rows:
        by_job[row.job_id].append(row)

    # Tally node entries (count of jobs that ever entered each stage)
    # and link transitions.
    node_counts: Counter[str] = Counter()
    link_counts: Counter[tuple[str, str]] = Counter()

    for job_id, history in by_job.items():
        # Apply the time window per-job: a job is "in" the window if at
        # least one of its transitions happened on/after window_start.
        # Drop entire jobs that don't qualify so the Sankey doesn't
        # show a partial journey ending mid-pipeline.
        if window_start is not None and not any(
            h.changed_at >= window_start for h in history
        ):
            continue

        for h in history:
            node_counts[h.to_status] += 1
            if h.from_status is not None:
                link_counts[(h.from_status, h.to_status)] += 1

    # Build nodes in canonical order so the rendering library doesn't
    # need to know about stage semantics. We only emit nodes that have
    # at least one job — Plotly will happily render an empty node, but
    # the visual gets noisy fast.
    nodes = [
        FunnelNode(id=stage, label=STAGE_LABELS[stage], count=node_counts[stage])
        for stage in STAGE_LABELS
        if node_counts[stage] > 0
    ]

    links = [
        FunnelLink(source=src, target=tgt, value=count)
        for (src, tgt), count in link_counts.items()
    ]

    return FunnelOut(
        nodes=nodes,
        links=links,
        total_jobs=len(by_job),
        window_start=window_start,
        window_end=now,
    )
