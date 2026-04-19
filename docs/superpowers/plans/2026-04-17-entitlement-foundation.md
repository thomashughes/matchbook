# Entitlement Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-user quotas for the two paid AI features (company research + job search) via a new DB table, two async helpers, and a 402 response contract. No Stripe and no UI yet.

**Architecture:** One Alembic migration adds 5 columns to `users` and creates `feature_usage`. A new `app/core/entitlement.py` exposes `check_quota` and `record_usage` used explicitly at route entry/exit. `/jobs/{id}/company-research` POST becomes the first caller; `/search` (sub-project D) will follow the same pattern.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, Postgres (enum + check constraints), Docker Compose.

**Spec:** `docs/superpowers/specs/2026-04-17-entitlement-foundation-design.md`

## Testing approach

This codebase has no pytest suite today (no `backend/tests/`, no pytest in `requirements.txt`). The established pattern is to verify via:

- `docker compose logs --tail=80 backend` after each rebuild
- `docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -c "..."` for DB assertions
- `curl` (or httpie) against the running backend on `http://localhost:3086`

Every task ends with a concrete verification command whose expected output is named. Don't skip them — "it builds" is not evidence that it works.

---

## File Structure

**Create:**
- `backend/alembic/versions/20260417_1000_entitlement.py` — migration adding columns + `feature_usage` table.
- `backend/app/models/feature_usage.py` — ORM model for the usage log.
- `backend/app/core/entitlement.py` — the `Feature` type, `QUOTAS` dict, `check_quota`, `record_usage`.

**Modify:**
- `backend/app/models/user.py` — add `subscription_tier`, `stripe_customer_id`, `stripe_subscription_id`, `current_period_start`, `current_period_end`.
- `backend/app/models/__init__.py` — export the new `FeatureUsage` so Alembic's metadata import sees it (only if the file currently lists other models explicitly).
- `backend/app/api/routes/company_research.py` — call `check_quota` before generation and `record_usage` after.

**Do not touch (this sub-project):**
- Frontend code. The 402 body is delivered; nothing renders it yet — that's sub-project C.
- Stripe code. There is none; we're setting up the seam it'll plug into later.
- The `/jobs` GET/create/update endpoints. Usage only counts paid AI operations.

---

### Task 1: Baseline — confirm the working tree is clean and services are up

**Files:** none.

- [ ] **Step 1: Confirm a clean working tree on the current branch**

Run: `git status`
Expected: `nothing to commit, working tree clean` on branch `feature/multi-tenant` (or whatever the user's current feature branch is).

If dirty, stop and ask the user — don't start entitlement work on top of unrelated uncommitted changes.

- [ ] **Step 2: Bring the stack up if it isn't already**

Run: `docker compose up -d`
Expected: `Container matchbookv2-postgres-1  Running` (and frontend/backend/redis similarly). Takes <5s when images already exist.

- [ ] **Step 3: Confirm backend is healthy**

Run: `curl -s http://localhost:3086/healthz`
Expected: `{"status":"ok"}` (or whatever the current `/healthz` returns — just not a 502 or timeout).

- [ ] **Step 4: Confirm current head migration is `0002_job_ai_outputs`**

Run: `docker compose exec backend alembic current`
Expected: something matching `0002_job_ai_outputs (head)`.

If not, investigate — the plan assumes we're adding revision `0003` on top of `0002`.

---

### Task 2: Alembic migration — add user columns + feature_usage table

**Files:**
- Create: `backend/alembic/versions/20260417_1000_entitlement.py`

- [ ] **Step 1: Create the migration file**

Create `backend/alembic/versions/20260417_1000_entitlement.py` with exactly this content:

```python
"""entitlement — user subscription_tier + feature_usage log

Adds five columns to users (tier + stripe ids + period window) and a new
feature_usage table that logs each paid AI operation. See
docs/superpowers/specs/2026-04-17-entitlement-foundation-design.md for
the shape decisions.

Revision ID: 0003_entitlement
Revises: 0002_job_ai_outputs
Create Date: 2026-04-17 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_entitlement"
down_revision: Union[str, None] = "0002_job_ai_outputs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Postgres enum for tier. create_type=False on the Column below means the
# type is managed explicitly here — this gives us clean ordering
# (create type, add column referencing it, drop column, drop type).
tier_enum = postgresql.ENUM(
    "free", "pro", "unlimited", name="subscription_tier_enum"
)


def upgrade() -> None:
    # 1. Create the enum type first so the column referencing it is valid.
    tier_enum.create(op.get_bind(), checkfirst=True)

    # 2. Extend users. server_default='free' backfills every existing row
    #    atomically as part of the ALTER — no separate data migration.
    op.add_column(
        "users",
        sa.Column(
            "subscription_tier",
            postgresql.ENUM(
                "free", "pro", "unlimited",
                name="subscription_tier_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="free",
        ),
    )
    op.add_column(
        "users", sa.Column("stripe_customer_id", sa.String(60), nullable=True)
    )
    op.add_column(
        "users", sa.Column("stripe_subscription_id", sa.String(60), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
    )

    # 3. Usage log. See spec §'New table feature_usage' for why a log
    #    (not a counter). CASCADE on user_id because GDPR delete must
    #    wipe usage history alongside the user row.
    op.create_table(
        "feature_usage",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("feature", sa.String(30), nullable=False),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Check constraint keeps bad feature names out at the DB layer.
        sa.CheckConstraint(
            "feature IN ('company_research', 'job_search')",
            name="ck_feature_usage_feature",
        ),
    )
    # Hot read path: COUNT(*) WHERE user_id=? AND feature=? AND used_at >= ?
    op.create_index(
        "ix_feature_usage_user_feature",
        "feature_usage",
        ["user_id", "feature"],
    )
    # Ops queries ("how many lookups last week"): cheap to add now.
    op.create_index(
        "ix_feature_usage_used_at", "feature_usage", ["used_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_feature_usage_used_at", table_name="feature_usage")
    op.drop_index("ix_feature_usage_user_feature", table_name="feature_usage")
    op.drop_table("feature_usage")

    op.drop_column("users", "current_period_end")
    op.drop_column("users", "current_period_start")
    op.drop_column("users", "stripe_subscription_id")
    op.drop_column("users", "stripe_customer_id")
    op.drop_column("users", "subscription_tier")

    tier_enum.drop(op.get_bind(), checkfirst=True)
```

- [ ] **Step 2: Rebuild the backend image so Alembic picks up the new file and runs it on start**

Run: `docker compose up -d --build backend`
Expected: build completes; container enters `Up` state within ~30s.

- [ ] **Step 3: Confirm the migration ran cleanly**

Run: `docker compose logs --tail=100 backend | grep -i alembic`
Expected: a line like `Running upgrade 0002_job_ai_outputs -> 0003_entitlement, entitlement`. No tracebacks.

- [ ] **Step 4: Confirm the schema is live**

Run:
```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\d users"
```
Expected: the output lists `subscription_tier`, `stripe_customer_id`, `stripe_subscription_id`, `current_period_start`, `current_period_end` among the columns. `subscription_tier` shows `subscription_tier_enum` as type and `'free'::subscription_tier_enum` as default.

Run:
```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\d feature_usage"
```
Expected: table exists with columns `id, user_id, feature, used_at`, indexes `ix_feature_usage_user_feature` and `ix_feature_usage_used_at`, and check constraint `ck_feature_usage_feature`.

- [ ] **Step 5: Confirm existing users were backfilled to 'free'**

Run:
```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT subscription_tier, COUNT(*) FROM users GROUP BY 1"
```
Expected: one row, `free | <n>` where `<n>` is the total user count. If there are 0 users, that's fine — the column default still applies to new inserts.

- [ ] **Step 6: Round-trip — downgrade then upgrade to catch reversibility bugs**

Run:
```bash
docker compose exec backend alembic downgrade -1 && \
docker compose exec backend alembic upgrade head
```
Expected: both commands succeed. Re-run Step 4's `\d feature_usage` to confirm the table is back.

If the downgrade fails, read the error — usually it's a lingering dependency (e.g., the enum type still referenced somewhere). Fix the migration and re-run; don't skip this check.

- [ ] **Step 7: Commit**

```bash
git add backend/alembic/versions/20260417_1000_entitlement.py
git commit -m "feat(db): add subscription tier + feature_usage log

Extends users with tier/stripe ids/period window and adds a new
feature_usage table. Lays the schema foundation for sub-project A of
the SaaS roadmap; no app code yet reads or writes these columns."
```

---

### Task 3: Extend the User ORM model

**Files:**
- Modify: `backend/app/models/user.py`

- [ ] **Step 1: Replace the file with the extended version**

Replace the full contents of `backend/app/models/user.py` with:

```python
"""
The User model — root of every tenant's data graph.

Tenancy note:
    This is a multi-tenant app with per-user isolation. Every data table
    that follows has a user_id FK → users(id) with CASCADE DELETE. That
    cascade matters — deleting a user must remove every trace (GDPR Art.
    17 right-to-erasure). We enforce the WHERE user_id = :current_user_id
    filter at the ORM/dependency layer too, belt-and-braces.
"""

from datetime import datetime
from typing import Literal

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


# Mirror the Postgres enum type created by migration 0003_entitlement.
# create_type=False — the migration already created the type; the model
# just references it. Keeping the values in sync with the migration is
# mechanical; if this drifts, Alembic autogenerate will flag it.
SubscriptionTier = Literal["free", "pro", "unlimited"]
_tier_pg_enum = PGENUM(
    "free", "pro", "unlimited",
    name="subscription_tier_enum",
    create_type=False,
)


class User(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "users"

    # Email is the login identifier. UNIQUE at the DB level so a race
    # between two concurrent registrations can't create duplicates — one
    # of them gets an IntegrityError and the route converts it to 409.
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # bcrypt hash, NOT the plaintext. Never store plaintext anywhere, ever.
    # 255 chars is plenty; a bcrypt hash is 60 characters.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Users start unverified. Most protected features (job scoring, CV
    # upload) should also require is_verified — enforced at the dep layer,
    # not here, so we can carve out exceptions if needed.
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Fernet-encrypted Google OAuth credentials (refresh token + access
    # token). Stored as TEXT because Fernet output is base64. Encryption
    # at rest means a DB dump alone can't be used to impersonate users'
    # Google accounts — the FERNET_KEY is required and lives only in env.
    google_calendar_credentials: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Subscription + billing --------------------------------------
    # See spec §'Columns added to users'. subscription_tier is the
    # primary switch that drives quota lookup; the four stripe_* /
    # period_* columns are populated by sub-project C's webhook.
    subscription_tier: Mapped[SubscriptionTier] = mapped_column(
        _tier_pg_enum, nullable=False, server_default="free"
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

- [ ] **Step 2: Rebuild backend and confirm it starts**

Run: `docker compose up -d --build backend`
Then: `docker compose logs --tail=60 backend`
Expected: backend comes up; no `sqlalchemy.exc.ArgumentError`, no `ImportError`. If Alembic prints `Target database is not up to date` or any schema mismatch, read the message and fix the model to match the migration.

- [ ] **Step 3: Smoke-test login still works**

Run (replace email/password with a known dev user — if none exists, register one via the frontend first):
```bash
curl -s -X POST http://localhost:3086/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"dev@example.com","password":"devpassword"}'
```
Expected: a JSON body with `access_token`. If this 500s, the model change broke something — check backend logs before continuing.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/user.py
git commit -m "feat(models): surface subscription_tier + billing columns on User

ORM now reflects the schema added in 0003_entitlement. No behaviour
change; downstream code doesn't read these fields yet."
```

---

### Task 4: Create the FeatureUsage ORM model

**Files:**
- Create: `backend/app/models/feature_usage.py`
- Modify: `backend/app/models/__init__.py` (only if it currently imports other model modules explicitly — see Step 1)

- [ ] **Step 1: Check whether models are auto-discovered or explicitly imported**

Run: `cat /Users/thomashughes/Desktop/Projects/matchbookv2/backend/app/models/__init__.py`

If the file is empty or only has a docstring, model files are discovered via Alembic's `env.py` + wildcard imports elsewhere — no change needed here, skip to Step 2.

If the file contains explicit imports like `from app.models.user import User`, you'll need to add a matching line in Step 3.

- [ ] **Step 2: Create the FeatureUsage model**

Create `backend/app/models/feature_usage.py` with:

```python
"""
FeatureUsage — one row per paid AI operation, per user.

Why a log (not a running counter):
    Count-on-read gives us an auditable trail AND the ability to forgive
    usage (promo, bug refund) by deleting rows, without schema changes.
    At the scale of this app (quotas top out at 100/period) the indexed
    COUNT(*) query is effectively O(log n) and not worth optimising.

Why the CHECK constraint on feature:
    Keeps unknown feature strings out of the log at the DB layer. If we
    ever add a third paid feature, update the check constraint in a
    migration alongside the code change — matching pairs.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPkMixin


class FeatureUsage(Base, UUIDPkMixin):
    __tablename__ = "feature_usage"
    __table_args__ = (
        CheckConstraint(
            "feature IN ('company_research', 'job_search')",
            name="ck_feature_usage_feature",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Kept as String, not a Python Literal — the DB check constraint is
    # the authority; the Feature Literal lives in app/core/entitlement.py
    # and typechecks callers, not stored rows.
    feature: Mapped[str] = mapped_column(String(30), nullable=False)
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
```

- [ ] **Step 3: (Only if Step 1 showed explicit imports) register the new model**

Add to `backend/app/models/__init__.py`:

```python
from app.models.feature_usage import FeatureUsage  # noqa: F401
```

Skip this step if models are auto-discovered.

- [ ] **Step 4: Rebuild backend and confirm it starts**

Run: `docker compose up -d --build backend`
Then: `docker compose logs --tail=60 backend`
Expected: clean startup, no SQLA errors.

- [ ] **Step 5: Smoke-check that Alembic now sees metadata consistent with DB**

Run: `docker compose exec backend alembic check`
Expected: `No new upgrade operations detected.` If Alembic reports a diff, the model definition has drifted from the migration — compare types, nullability, indexes, and constraints, and fix the model until `alembic check` is clean. Do NOT autogenerate a new migration to paper over the drift.

Note: some Alembic versions don't have `check`. If so, run `docker compose exec backend alembic revision --autogenerate -m tmp_check`, inspect the generated file for any non-empty `upgrade()` body, then delete the file. An empty body = clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/feature_usage.py backend/app/models/__init__.py
git commit -m "feat(models): add FeatureUsage ORM model

One row per paid AI operation. Read via count queries in
app/core/entitlement.py (next commit)."
```

---

### Task 5: The QUOTAS dict and Feature type

**Files:**
- Create: `backend/app/core/entitlement.py` (skeleton only — helpers land in Tasks 6 + 7)

- [ ] **Step 1: Create the skeleton file**

Create `backend/app/core/entitlement.py` with:

```python
"""
Entitlement — per-user quota enforcement for paid AI features.

Two async helpers used at route boundaries:

    await check_quota(user, feature, db)   # raises 402 if over
    # ... run the expensive operation ...
    await record_usage(user, feature, db)  # adds one row (no commit)

See docs/superpowers/specs/2026-04-17-entitlement-foundation-design.md
for the full design (why a log, why 402, how the period is chosen).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.models.user import User

Feature = Literal["company_research", "job_search"]

# Single source of truth for tier limits. Changing a number here is a
# code-only change — no migration. The pricing page (sub-project C) will
# read these same values, DRY.
QUOTAS: dict[str, dict[Feature, int]] = {
    "free":      {"company_research": 3,   "job_search": 3},
    "pro":       {"company_research": 10,  "job_search": 10},
    "unlimited": {"company_research": 100, "job_search": 100},
}


def period_start_for(user: User) -> datetime:
    """Return the timestamp from which to count usage for this user.

    Free tier: all-time (uses users.created_at). This implements the
    pricing-page promise that the 3 lifetime allowances are spent once,
    not refilled on downgrade.

    Paid tier: the anniversary window opened by the most recent billing
    cycle. current_period_start is populated by Stripe webhooks in
    sub-project C; until then it stays NULL and no user should be on
    'pro' or 'unlimited' in the DB.
    """
    if user.subscription_tier == "free":
        return user.created_at
    if user.current_period_start is None:
        # A paid-tier row with no period window is a data bug — fail
        # loud rather than silently bucket usage against some default.
        raise RuntimeError(
            f"User {user.id} is tier={user.subscription_tier} but has "
            "current_period_start=NULL. Billing sync is inconsistent."
        )
    return user.current_period_start
```

- [ ] **Step 2: Rebuild backend and confirm the import compiles**

Run: `docker compose up -d --build backend && docker compose logs --tail=30 backend`
Expected: no `ImportError`, no `SyntaxError`.

- [ ] **Step 3: Quick interactive check inside the container**

Run:
```bash
docker compose exec backend python -c "
from app.core.entitlement import QUOTAS, period_start_for, Feature
assert QUOTAS['free']['company_research'] == 3
assert QUOTAS['pro']['job_search'] == 10
assert QUOTAS['unlimited']['company_research'] == 100
print('quotas ok')
"
```
Expected: prints `quotas ok`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/entitlement.py
git commit -m "feat(entitlement): add Feature type and QUOTAS table

Single source of truth for tier limits. Helpers land next."
```

---

### Task 6: Implement check_quota

**Files:**
- Modify: `backend/app/core/entitlement.py` (append the helper)

- [ ] **Step 1: Append the check_quota helper**

Append to `backend/app/core/entitlement.py`:

```python
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature_usage import FeatureUsage


async def check_quota(
    user: User, feature: Feature, db: AsyncSession
) -> None:
    """Raise 402 if the user has exhausted their allowance for this feature.

    Returns None on success — the caller continues into the paid op.

    The 402 body follows the contract in the spec:
        detail = {error, feature, used, limit, tier, upgrade_url}
    FastAPI serialises this as response JSON {"detail": {...}}, which
    the frontend's ApiError already carries via its `detail` field.
    """
    limit = QUOTAS[user.subscription_tier][feature]
    since = period_start_for(user)

    result = await db.execute(
        select(func.count())
        .select_from(FeatureUsage)
        .where(
            FeatureUsage.user_id == user.id,
            FeatureUsage.feature == feature,
            FeatureUsage.used_at >= since,
        )
    )
    used = int(result.scalar() or 0)

    if used >= limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "quota_exceeded",
                "feature": feature,
                "used": used,
                "limit": limit,
                "tier": user.subscription_tier,
                "upgrade_url": "/account/billing",
            },
        )
```

- [ ] **Step 2: Rebuild backend**

Run: `docker compose up -d --build backend && docker compose logs --tail=30 backend`
Expected: clean start.

- [ ] **Step 3: Verify check_quota lets an under-quota user through**

Run inside the backend container — this uses the app's own async machinery so behaviour matches production:
```bash
docker compose exec backend python -c "
import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.entitlement import check_quota
from app.models.user import User

async def main():
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one()
        await check_quota(user, 'company_research', db)
        print(f'user {user.email} tier={user.subscription_tier} -> passed')

asyncio.run(main())
"
```
Expected: `user <email> tier=free -> passed`.

If the error is `NoResultFound`, you need at least one user in the DB — register one via the frontend and retry.

If the import path `AsyncSessionLocal` is wrong, inspect `backend/app/core/database.py` and use whatever the existing sessionmaker is called there.

- [ ] **Step 4: Verify check_quota raises 402 when at/over quota**

Run:
```bash
docker compose exec backend python -c "
import asyncio
from fastapi import HTTPException
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.entitlement import check_quota
from app.models.user import User
from app.models.feature_usage import FeatureUsage

async def main():
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one()

        # Seed 3 usages for this user
        for _ in range(3):
            db.add(FeatureUsage(user_id=user.id, feature='company_research'))
        await db.commit()

        try:
            await check_quota(user, 'company_research', db)
            print('FAIL: no 402 raised')
        except HTTPException as e:
            assert e.status_code == 402, e
            d = e.detail
            assert d['error'] == 'quota_exceeded'
            assert d['feature'] == 'company_research'
            assert d['used'] == 3
            assert d['limit'] == 3
            assert d['tier'] == 'free'
            assert d['upgrade_url'] == '/account/billing'
            print('402 shape ok')

        # Clean up so later tasks start from a known state
        await db.execute(
            FeatureUsage.__table__.delete().where(
                FeatureUsage.user_id == user.id
            )
        )
        await db.commit()

asyncio.run(main())
"
```
Expected: `402 shape ok`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/entitlement.py
git commit -m "feat(entitlement): implement check_quota

Counts feature_usage rows since the tier's period start and raises
402 Payment Required with a structured body when at/over the limit."
```

---

### Task 7: Implement record_usage

**Files:**
- Modify: `backend/app/core/entitlement.py` (append the helper)

- [ ] **Step 1: Append record_usage**

Append to `backend/app/core/entitlement.py`:

```python
async def record_usage(
    user: User, feature: Feature, db: AsyncSession
) -> None:
    """Insert one feature_usage row for this user+feature.

    Does NOT commit — the caller is responsible for batching this into
    the same transaction as the operation's primary write (e.g., the
    company research cache row), so we only bill on full success.
    """
    db.add(FeatureUsage(user_id=user.id, feature=feature))
    await db.flush()
```

Note: `await db.flush()` forces the INSERT to go over the wire so a later `db.commit()` call by the route commits everything atomically. Without `flush()`, the row would still land at commit time — but flushing now means any constraint violation (e.g., a bogus `feature` value the CHECK rejects) surfaces at the call site, not deep inside the commit.

- [ ] **Step 2: Rebuild backend**

Run: `docker compose up -d --build backend && docker compose logs --tail=30 backend`
Expected: clean start.

- [ ] **Step 3: Verify record_usage inserts a row**

Run:
```bash
docker compose exec backend python -c "
import asyncio
from sqlalchemy import select, func
from app.core.database import AsyncSessionLocal
from app.core.entitlement import record_usage
from app.models.user import User
from app.models.feature_usage import FeatureUsage

async def main():
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one()
        before = (await db.execute(
            select(func.count()).select_from(FeatureUsage)
            .where(FeatureUsage.user_id == user.id,
                   FeatureUsage.feature == 'company_research')
        )).scalar_one()

        await record_usage(user, 'company_research', db)
        await db.commit()

        after = (await db.execute(
            select(func.count()).select_from(FeatureUsage)
            .where(FeatureUsage.user_id == user.id,
                   FeatureUsage.feature == 'company_research')
        )).scalar_one()

        assert after == before + 1, f'before={before} after={after}'
        print(f'record_usage ok (before={before} after={after})')

        # Clean up
        await db.execute(
            FeatureUsage.__table__.delete().where(
                FeatureUsage.user_id == user.id
            )
        )
        await db.commit()

asyncio.run(main())
"
```
Expected: `record_usage ok (before=0 after=1)` (or similar incrementing numbers).

- [ ] **Step 4: Verify the CHECK constraint rejects bad feature names**

Run:
```bash
docker compose exec backend python -c "
import asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.core.database import AsyncSessionLocal
from app.core.entitlement import record_usage
from app.models.user import User

async def main():
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one()
        try:
            # Cast via Python to bypass the Feature Literal — Typing
            # is advisory, the DB is the authority.
            await record_usage(user, 'bogus_feature', db)  # type: ignore
            print('FAIL: CHECK did not reject bogus feature')
        except IntegrityError:
            print('CHECK constraint ok')
        finally:
            await db.rollback()

asyncio.run(main())
"
```
Expected: `CHECK constraint ok`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/entitlement.py
git commit -m "feat(entitlement): implement record_usage

Inserts one feature_usage row and flushes (no commit). Caller batches
the row into the same transaction as the primary operation's write so
we only bill on full success."
```

---

### Task 8: Wire entitlement into the company-research route

**Files:**
- Modify: `backend/app/api/routes/company_research.py`

- [ ] **Step 1: Add the import**

In `backend/app/api/routes/company_research.py`, add alongside the other `app.core` imports:

```python
from app.core.entitlement import check_quota, record_usage
```

- [ ] **Step 2: Insert check_quota and record_usage into `generate_company_research`**

Replace the body of `generate_company_research` (starts around line 160 in `company_research.py`) with the version below. The two new lines are `check_quota(...)` at the top and `record_usage(...)` just before `db.commit()`:

```python
@router.post(
    "",
    response_model=CompanyResearchOut,
    status_code=status.HTTP_200_OK,
    # rate_limit_ai applies because POST always spends on web_search —
    # this is the only path that incurs cost. GET is free.
    dependencies=[Depends(rate_limit_ai)],
)
async def generate_company_research(
    job_id: UUID,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> CompanyResearchOut:
    """Generate (or regenerate) a briefing via Claude + web search.

    Writes to the shared cache, upserting on normalised company_name.
    Always runs — POST is the 'I explicitly want this' verb. Clients
    that just want to read cached data should use GET.
    """
    # Quota gate first, before job lookup — no point touching the DB
    # or Claude if the user has no allowance left. The 402 body tells
    # the frontend exactly what to show.
    await check_quota(user, "company_research", db)

    job = await _own_job(job_id, user, db)
    company = _resolve_company(job)
    normalized = _norm(company)
    now = datetime.now(timezone.utc)

    # Trim the JD before passing it as context. Full raw JDs can carry
    # thousands of tokens of boilerplate (benefits, EEO, legal) that add
    # nothing to the research bias and everything to the bill. Role +
    # team signal typically sits in the first ~1500 chars.
    jd_context = (job.description_raw or "")[:JD_CONTEXT_MAX_CHARS] or None

    briefing, sources = await complete_text_with_web_search(
        system=research_prompt.SYSTEM,
        user=research_prompt.build_user_message(
            company=company,
            job_description=jd_context,
        ),
        max_tokens=4096,
        max_searches=2,
    )

    # Belt-and-braces: despite the "no preamble" instruction, Claude
    # sometimes narrates progress in the final text block before emitting
    # the OVERVIEW header. Drop everything before the first OVERVIEW line
    # so the cached briefing starts cleanly.
    overview_match = re.search(r"^OVERVIEW\s*$", briefing, re.MULTILINE)
    if overview_match:
        briefing = briefing[overview_match.start() :].rstrip()

    expires_at = now + CACHE_TTL
    research_data = {"briefing": briefing, "sources": sources}

    stmt = (
        pg_insert(CompanyResearchCache)
        .values(
            company_name=normalized,
            research_data=research_data,
            cached_at=now,
            expires_at=expires_at,
        )
        .on_conflict_do_update(
            index_elements=[CompanyResearchCache.company_name],
            set_={
                "research_data": research_data,
                "cached_at": now,
                "expires_at": expires_at,
            },
        )
        .returning(CompanyResearchCache)
    )
    result = await db.execute(stmt)
    row = result.scalar_one()

    # Bill only after the research row is staged. record_usage flushes
    # but doesn't commit, so the single commit below atomically lands
    # both the cache row and the usage row — we charge the user iff
    # the operation fully succeeded.
    await record_usage(user, "company_research", db)
    await db.commit()

    return _to_out(row, fresh=True)
```

- [ ] **Step 3: Rebuild backend**

Run: `docker compose up -d --build backend && docker compose logs --tail=40 backend`
Expected: clean start, no import errors.

- [ ] **Step 4: End-to-end — first research call succeeds and records usage**

You need a valid access token for a verified user whose job has a `company` field set. Register + verify via the frontend (or inspect the backend log for the verification link in dev), log in, grab the token, and save the job's UUID.

```bash
TOKEN="<paste-access-token>"
JOB_ID="<paste-job-uuid>"

# 1. Confirm current usage count is 0
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT COUNT(*) FROM feature_usage WHERE feature='company_research'"
# Expected: 0 (or whatever you started with — note it)

# 2. Fire the POST
curl -s -X POST "http://localhost:3086/api/v1/jobs/$JOB_ID/company-research" \
  -H "Authorization: Bearer $TOKEN"
# Expected: a JSON body with briefing / sources / cached_at / expires_at / fresh=true

# 3. Confirm one feature_usage row was written
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT COUNT(*) FROM feature_usage WHERE feature='company_research'"
# Expected: previous count + 1
```

- [ ] **Step 5: End-to-end — fourth call returns 402 with the contract body**

Continuing from the same token. Run research twice more (so the user has used it 3 times total — the free quota), then attempt a 4th:

```bash
# Calls 2 and 3 (each will re-upsert the cache; that's fine)
curl -s -X POST "http://localhost:3086/api/v1/jobs/$JOB_ID/company-research" \
  -H "Authorization: Bearer $TOKEN" > /dev/null
curl -s -X POST "http://localhost:3086/api/v1/jobs/$JOB_ID/company-research" \
  -H "Authorization: Bearer $TOKEN" > /dev/null

# Call 4 — should be 402
curl -si -X POST "http://localhost:3086/api/v1/jobs/$JOB_ID/company-research" \
  -H "Authorization: Bearer $TOKEN"
```

Expected: first line `HTTP/1.1 402 Payment Required`. Body:

```json
{
  "detail": {
    "error": "quota_exceeded",
    "feature": "company_research",
    "used": 3,
    "limit": 3,
    "tier": "free",
    "upgrade_url": "/account/billing"
  }
}
```

Also confirm the 4th call did NOT add a row:

```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT COUNT(*) FROM feature_usage WHERE feature='company_research'"
# Expected: 3 (unchanged from Step 4 end)
```

- [ ] **Step 6: End-to-end — bumping tier lets the user through again**

Manually promote the user and verify the 402 becomes a 200:

```bash
# Grant pro and set a period window (simulates what Stripe webhook will do later)
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
UPDATE users SET
  subscription_tier = 'pro',
  current_period_start = now(),
  current_period_end   = now() + interval '30 days'
WHERE email = 'dev@example.com';
"

# Retry — should now succeed (pro = 10/month, and used=0 in this period since
# current_period_start just moved to now)
curl -si -X POST "http://localhost:3086/api/v1/jobs/$JOB_ID/company-research" \
  -H "Authorization: Bearer $TOKEN" | head -1
# Expected: HTTP/1.1 200 OK
```

Then revert so later testing starts clean:

```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
UPDATE users SET
  subscription_tier = 'free',
  current_period_start = NULL,
  current_period_end   = NULL
WHERE email = 'dev@example.com';

DELETE FROM feature_usage WHERE feature = 'company_research';
"
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/company_research.py
git commit -m "feat(company-research): gate POST on entitlement quota

Adds check_quota before generation and record_usage after the cache
upsert. The single db.commit() atomically lands both rows, so we only
bill on full success."
```

---

### Task 9: End-of-sub-project verification sweep

**Files:** none — this is a final confidence check.

- [ ] **Step 1: Fresh-build both services and confirm they come up clean**

Run: `docker compose up -d --build && docker compose logs --tail=60 backend && docker compose logs --tail=30 frontend`
Expected: no tracebacks, no TS build failures (frontend is unaffected but we confirm nothing else regressed).

- [ ] **Step 2: Confirm migration state**

Run: `docker compose exec backend alembic current`
Expected: `0003_entitlement (head)`.

- [ ] **Step 3: Confirm cold-user flow still works**

Register a brand-new user via the frontend. Confirm in the DB that they default to `free`:

```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT email, subscription_tier, current_period_start FROM users ORDER BY created_at DESC LIMIT 1"
```
Expected: `free | <null>`.

- [ ] **Step 4: Confirm the unrelated route `/jobs/{id}/score` is NOT gated**

Entitlement only covers company research + job search. The scoring pipeline stays free:

```bash
curl -si -X POST "http://localhost:3086/api/v1/jobs/$JOB_ID/score" \
  -H "Authorization: Bearer $TOKEN" | head -1
```
Expected: `HTTP/1.1 200 OK` (assuming the user owns the job) — not 402. If this 402s, you accidentally wired entitlement into the wrong route; inspect `backend/app/api/routes/jobs.py` and revert.

- [ ] **Step 5: Open a PR or tag the branch**

Run: `git log --oneline -10`
Expected: roughly 7 commits from this sub-project (one per task, Task 1 had no commit, Task 9 has none). If ready to PR, push and open one. If continuing into sub-project B, keep the branch and move on — each sub-project gets its own commit range.

No commit in this task.

---

## Self-review pass

**Spec coverage:**
- §Non-goals — no Stripe, no UI, no backfill ✓ (none of the tasks touch these).
- §Data model columns on users ✓ Task 2 + 3.
- §feature_usage table ✓ Task 2 + 4.
- §QUOTAS dict ✓ Task 5.
- §`check_quota` / `record_usage` / `period_start_for` ✓ Tasks 5–7.
- §402 response contract (all six fields) ✓ Task 6 Step 1 + Task 8 Step 5.
- §Route wiring (commit-after-flush ordering) ✓ Task 8 Step 2.
- §Migration safety (rollback round-trip) ✓ Task 2 Step 6.
- §Race / double-charge — spec explicitly accepts it; no task required.

**Type consistency:**
- `Feature = Literal["company_research", "job_search"]` used identically in Tasks 5, 6, 7, 8.
- `check_quota(user, feature, db) -> None` signature matches the spec and every call site.
- `record_usage(user, feature, db) -> None` signature matches the spec and every call site.
- Tier strings `"free" | "pro" | "unlimited"` match the Postgres enum values and the `QUOTAS` keys.

**Placeholder scan:** no TBDs, no "handle edge cases", every code step shows complete code, every verify step names expected output.

No gaps — moving to handoff.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-17-entitlement-foundation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
