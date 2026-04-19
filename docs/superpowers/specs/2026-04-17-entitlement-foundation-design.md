# Entitlement foundation — design

**Date:** 2026-04-17
**Status:** Awaiting user review. No code yet.
**Sub-project:** A (first of five — see `2026-04-17-matchbook-saas-overview.md`)

## Goal

Land the DB schema, server-side helpers, and HTTP contract that gate the
two paid features (company research + claude job search) behind a
per-user quota. This sub-project ships **no UI** and introduces **no
paywall screens** — it's the foundation everything else plugs into.

After this lands: every existing user is on `free`, the
`/company-research` endpoint counts their usage, and a 4th hit returns
402 with a structured body the frontend can branch on. The upgrade flow
to turn 402 into a Stripe Checkout session is sub-project C's job.

## Why this order

Doing quotas first (ahead of billing, ahead of new features) is the
only sequence that avoids rework:

- **If we built Stripe first:** we'd need to fake out the quota check
  with a stub, then rip out the stub later. More code churn than just
  defining the contract now.
- **If we built the job-search feature first:** we'd have to add a
  second gate later — and retrofit quota checks onto a live endpoint.
  Easier to gate from day one.
- **If we built Stripe and the feature at the same time:** three moving
  parts in one PR, high blast radius, hard to roll back.

Entitlement is the seam. Everything upstream (billing) and downstream
(features) clips onto it.

## Non-goals

To keep this shippable on its own:

- No Stripe integration yet — tiers are stored in the DB but no one can
  move off `free` without a manual admin UPDATE. That's fine for the
  interim.
- No account / billing page. The 402 response exists but nothing renders
  it yet.
- No backfill of historical usage. Existing users who already ran
  company research "for free" keep that — we start counting from the
  migration date.
- No admin tooling for comp tiers / promo codes / trials. Deferred until
  C is in.
- No Chrome extension PAT scaffolding — that's sub-project B.

## Architecture

Three new pieces:

1. **Schema extensions** — five columns on `users`, one new table
   `feature_usage`.
2. **`app/core/entitlement.py`** — two async helpers (`check_quota`,
   `record_usage`) plus a `QUOTAS` dict. Stateless, just pure DB
   reads/writes with no HTTP knowledge beyond raising `HTTPException`.
3. **Route wiring** — the existing `POST /jobs/{id}/company-research`
   endpoint calls `check_quota` before the Claude call and
   `record_usage` after it succeeds. The future `/search` endpoint will
   do the same.

That's it. No middleware, no decorators, no metaclass magic. Two
function calls, explicit at every call site. This beats a decorator
because the call site needs to know *where* to record usage (before or
after the expensive op) — decorators hide that choice.

## Data model

### Columns added to `users`

| Column | Type | Nullable | Default | Notes |
| - | - | - | - | - |
| `subscription_tier` | `tier_enum` | not null | `'free'` | Enum of `'free' \| 'pro' \| 'unlimited'`. |
| `stripe_customer_id` | `VARCHAR(60)` | null | — | Populated the first time a user opens Checkout. One customer per user forever. |
| `stripe_subscription_id` | `VARCHAR(60)` | null | — | Nulled when the sub is cancelled + period ends. |
| `current_period_start` | `TIMESTAMPTZ` | null | — | Paid tiers only. Used to bucket usage. |
| `current_period_end` | `TIMESTAMPTZ` | null | — | Paid tiers only. Used by `check_quota` to detect renewal. |

**Why a Postgres enum, not a free-text string:** enum invalidates a bad
value at INSERT time; if someone typos `'Pro'` the DB rejects it.
Migrating to a new tier later is an `ALTER TYPE ... ADD VALUE 'x'`
(two-line migration). The common objection — "enums are hard to change"
— applies to *renaming*, not *adding*. We won't rename.

**Why nullable period columns:** free users don't have a billing period.
Using `NULL` means "lifetime counting applies" and removes the need for
a sentinel date. The code branches on `tier == 'free'` anyway, so the
nullability is load-bearing documentation.

### New table `feature_usage`

| Column | Type | Notes |
| - | - | - |
| `id` | UUID PK | `gen_random_uuid()` default — matches the rest of the schema. |
| `user_id` | UUID FK → `users(id)` ON DELETE CASCADE | GDPR — deleting a user wipes their usage log. |
| `feature` | `VARCHAR(30)` with check constraint | Values: `'company_research'`, `'job_search'`. |
| `used_at` | `TIMESTAMPTZ` NOT NULL DEFAULT `now()` | The moment we charged against the quota. |

**Indices:**
- `ix_feature_usage_user_feature` on `(user_id, feature)` — the hot
  read path for `check_quota` is "count rows where user = X and feature
  = Y, filtered by timestamp".
- `ix_feature_usage_used_at` on `(used_at)` — supports future ops
  queries ("how many lookups happened last week"). Optional for v1 but
  cheap to add.

**Why a log table, not a counter column:** counters are a nightmare to
audit. With a log we can:
- Answer "did this user *actually* run 3 researches before being
  blocked?" from the data, not from trust.
- Compute "usage this period" and "lifetime usage" from the same table.
- Drop rows later if we want to forgive usage (promo, bug refund)
  without a migration.

The cost is a tiny bit more storage — negligible compared to the rest
of the DB. A user running 100 lookups/month = 1200 rows/year = trivial.

### Why not count by month-aggregate?

Rolling an aggregate table (`user_id, feature, month, count`) avoids
scanning logs but adds moving parts: you have to update two tables in
sync, or accept staleness. For a quota that tops out at 100, scanning
the log with an indexed query is fine. If we ever hit "running
aggregate over a million rows", re-evaluate — but that's a problem
worth having.

## The `QUOTAS` dict

Single source of truth in `app/core/entitlement.py`:

```python
QUOTAS: dict[str, dict[Feature, int]] = {
    "free":      {"company_research": 3,   "job_search": 3},
    "pro":       {"company_research": 10,  "job_search": 10},
    "unlimited": {"company_research": 100, "job_search": 100},
}
```

Where `Feature = Literal["company_research", "job_search"]`.

Changing a limit = edit this dict + redeploy. No migration needed
because the values aren't in the schema.

## The two helpers — contract

```python
async def check_quota(user: User, feature: Feature, db: AsyncSession) -> None:
    """Raise HTTPException(402) if the user has exhausted their allowance.

    Returns None on success — no body; the caller continues.

    The period the count is bucketed into depends on tier:
      - free: lifetime (count *ever* for this user)
      - pro/unlimited: from user.current_period_start to now

    Why count on read, not maintain a running number: see 'Why a log
    table' above. At these volumes the query is effectively O(log n).
    """

async def record_usage(user: User, feature: Feature, db: AsyncSession) -> None:
    """Insert one feature_usage row.

    Call AFTER the paid operation succeeds — if Claude raises or web
    search fails, we don't want to have billed the user.

    Does NOT commit; lets the caller batch this into the same
    transaction as the actual result (e.g., inserting the company
    research row). Everything or nothing.
    """
```

### Why "count on read" — concretely

The 402 check is one SQL:

```sql
SELECT COUNT(*) FROM feature_usage
WHERE user_id = :uid
  AND feature = :feature
  AND used_at >= :since
```

With the `(user_id, feature)` index, Postgres returns that in single-
digit ms even at high row counts per user.

The alternative — maintaining a `feature_counters` table and doing
`SELECT count FROM feature_counters WHERE user_id = :uid` — is faster
on paper but:
- has to be UPDATED inside `record_usage` (extra write path)
- needs a separate "reset counters at period rollover" job
- drifts from reality if the `feature_usage` log and the counter
  disagree (which *will* happen — reconciliation is painful)

Simplicity wins until measurements say otherwise.

### Where the "period start" comes from

```python
def period_start_for(user: User) -> datetime:
    if user.subscription_tier == "free":
        return user.created_at  # lifetime
    return user.current_period_start  # paid tier's anniversary window
```

Downgrade semantics fall out naturally: a user who was pro, used 5
lookups, then downgraded to free has `free` count-since-`created_at` —
which already includes those 5 — so they're over the free quota
forever. That's the "no free allowance after paying" rule the pricing
page promises. No special-case code; just arithmetic.

### Race / double-charge note

Two concurrent requests from the same user could both pass
`check_quota` and both insert a `feature_usage` row, effectively
getting "one free extra" past the quota. We accept this for v1:
- The window is milliseconds — humans don't trigger it. Bots might,
  but the rate limiter caps ai endpoints at 60/min.
- The worst case is one free extra lookup, not a quota bypass.
- Fixing it requires either `SELECT FOR UPDATE` on the user row (adds
  lock contention for the general case) or a pg advisory lock (extra
  code for a marginal gain).

If we ever catch this in the wild, wrap both calls in `SELECT ... FOR
UPDATE` on `users(id)` — minimal change.

## HTTP contract — the 402 response

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

Fields:
- `error` — enum-ish string for programmatic branching. Currently one
  value (`quota_exceeded`) but reserving the field lets us add
  `subscription_past_due` later without restructuring.
- `feature` — so the frontend can show "You've used all your company
  research lookups" instead of a generic message.
- `used` / `limit` — render as `3 / 3` on the paywall card.
- `tier` — so the frontend can show the right CTA (free→pro vs
  pro→unlimited).
- `upgrade_url` — where to send the user. Currently the account page;
  later this could become a Checkout session URL directly.

FastAPI convention: `HTTPException.detail` is whatever you stuff in. We
stuff a dict, which serialises to the `"detail": {...}` shape above.
The frontend's existing `ApiError` class already stores `detail` as
`unknown` — only tweak is `JSON.parse` on 402 responses.

### Status code choice — why 402, not 403 or 429

- `403 Forbidden` — wrong. The user *is* authenticated and has
  permission; they just ran out of allowance. Using 403 would mean
  intercepting every 403 in the frontend and inspecting the body to
  tell "actual permission denied" from "upgrade needed".
- `429 Too Many Requests` — wrong. 429 is for rate limiting (you're
  going too fast, wait). Retry-After is part of the standard. This is
  not that; no amount of waiting helps.
- `402 Payment Required` — literally what the RFC says: "reserved for
  future use… intended for digital payment systems". We are the future
  use. Stripe docs call 402 the right code for this. Clients don't
  special-case it, but we don't need them to.

## How this wires into the existing app

### `/jobs/{job_id}/company-research` POST

Current (abbreviated, see `backend/app/api/routes/jobs.py`):

```python
@router.post("/{job_id}/company-research", ...)
async def generate_company_research(job_id: UUID, user: User = ..., db: AsyncSession = ...):
    job = await _get_owned_job(db, job_id, user.id)
    research = await company_research_service.generate(job, db)
    return research
```

New:

```python
@router.post("/{job_id}/company-research", ...)
async def generate_company_research(job_id: UUID, user: User = ..., db: AsyncSession = ...):
    await check_quota(user, "company_research", db)  # raises 402 if over
    job = await _get_owned_job(db, job_id, user.id)
    research = await company_research_service.generate(job, db)
    await record_usage(user, "company_research", db)
    await db.commit()  # already commits inside service? — see note
    return research
```

**Commit ordering note:** if `generate()` already commits the research
row to the DB, we need to defer its commit or re-arrange so the
`record_usage` row and the research row land in the same transaction.
The plan will spell this out; the spec just names the constraint.

### The `/search` endpoint (sub-project D)

Won't exist until D. But the shape will be identical — quota check at
the top, record after success. The spec for D will reference this one.

## Testing

What the foundation must have green tests for before we move on:

1. **Migration round-trip** — `alembic upgrade head` on a fresh DB,
   then downgrade, then upgrade again. Catches reversibility bugs.
2. **Default tier** — a user registered post-migration has
   `subscription_tier = 'free'` and nullable billing columns.
3. **`check_quota` under quota** — returns None.
4. **`check_quota` exactly at quota** — raises 402 with the right
   `detail` shape (assert on `error`, `feature`, `used`, `limit`,
   `tier`, `upgrade_url`).
5. **`check_quota` counts lifetime for free, period for paid** — two
   parametrised cases:
   - Free user with 3 ancient usages → blocked.
   - Pro user with 3 usages before `current_period_start` → not
     blocked (new period).
6. **`record_usage` inserts exactly one row** — and does not commit
   (caller's responsibility).
7. **Route 402** — integration test: seed a free user with 3 usages,
   POST `/jobs/{id}/company-research`, assert status 402 and body.
8. **Route success path increments** — seed a free user with 0 usages,
   POST, assert status 200 and that one `feature_usage` row exists.

Tests live next to `backend/tests/test_entitlement.py` (unit) and
`backend/tests/test_jobs.py` (extended with the two route cases).

## Migration safety

The migration adds columns (non-blocking in Postgres as long as defaults
are constant) and creates a new table (instant). No locking of `users`
beyond the DDL instant. Users already in the DB get
`subscription_tier = 'free'` via the column default.

Rollback is a plain `DROP TABLE feature_usage` + drop columns + drop the
enum type. Order matters — drop columns before dropping the enum.

## What's still open (deferred to the plan)

- Exact shape of the Pydantic response schema class name for 402 (or
  whether we skip Pydantic since it's an error body).
- Whether `record_usage` takes an optional `at: datetime` param for
  tests (probably yes).
- Whether the enum is declared as `ENUM('free', 'pro', 'unlimited')`
  inline in the migration or via `postgresql.ENUM(..., create_type=...)`
  — both work; the plan will pick one.

None of these block agreement on the design.
