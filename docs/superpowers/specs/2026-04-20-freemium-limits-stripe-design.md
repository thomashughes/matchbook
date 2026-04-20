# Freemium entitlements + Stripe billing — design

**Date:** 2026-04-20
**Status:** Draft — awaiting approval before implementation plan.
**Scope:** Add plan-based monthly entitlements to all AI-consuming endpoints, with a paid tier unlocked via Stripe Checkout. Scaffold (but do not ship) the future AI-job-search feature so its quota slot is already in place.

## Goals

1. Cap free users to an allowance that keeps Anthropic spend near-zero per free user while still letting them evaluate every feature.
2. Sell a £7.99/mo paid tier that lifts caps high enough for a real job search without leaving theoretical abuse unbounded.
3. Display remaining credits in-context so users never hit an unexpected wall.
4. Leave Thomas (the developer account) permanently unthrottled.
5. Scaffold a future `ai_job_search` feature's quotas without adding dead code.

## Non-goals

- Annual plans. Users don't stay >~3 months.
- Team/org plans.
- Metered billing or overage charges.
- Any AI-job-search endpoint. Only its quota slot.
- Retroactive counting of historical data toward the current window.

## Entitlement matrix

Counter keys and limits — the single source of truth. Resource keys are the strings used as `resource` in the `usage_counters` table.

| Resource key | Scope | Free limit | Paid limit | Counted when |
|---|---|---|---|---|
| `jobs_created` | user | 5 / mo | 50 / mo | `POST /jobs`, `/jobs/from-pdf`, `/jobs/from-extension` succeeds |
| `company_research` | user | 3 / mo | 10 / mo | `POST /jobs/{id}/company-research` called — counts **even if served from cache** (see "Company research cache + quota" below). `GET` stays free (passive page load must not burn credits). |
| `draft_outreach` | (user, job) | 3 / mo | 10 / mo | `POST /jobs/{id}/ai-outputs/outreach` succeeds |
| `draft_form_response` | (user, job) | 3 / mo | 10 / mo | `POST /jobs/{id}/ai-outputs/form-response` succeeds |
| `draft_follow_up` | (user, job) | 3 / mo | 10 / mo | `POST /jobs/{id}/ai-outputs/follow-up` succeeds |
| `draft_interview_prep` | (user, job) | 3 / mo | 10 / mo | `POST /jobs/{id}/ai-outputs/interview-prep` succeeds |
| `cover_letter` | (user, job) | 3 / mo | 10 / mo | `POST /jobs/{id}/cover-letters` succeeds |
| `ai_job_search` *(scaffold only)* | user | 1 / mo | 5 / mo | *future* `POST /jobs/search-ai` — no route in this work |

`paid_grandfathered` plan bypasses all limits — used for the developer account only.

**Rescoring (`POST /jobs/{id}/score`) is exempt.** It's triggered after a profile edit and does not represent discretionary spend. Still protected by the existing 60/min burst limit.

## Window semantics

Each user's month window is anchored to their `user.created_at` day-of-month.

- `window_start` = last anchor day at or before `now()`, at 00:00 UTC.
- `window_end` = window_start + 1 calendar month, adjusted for short months (Jan 31 anchor → Feb 28/29, not Mar 3).
- Upgrade mid-window: window and usage counts are preserved. A user at 4/5 jobs free becomes 4/50 jobs paid — no fresh reset.
- Downgrade (via `customer.subscription.deleted` or end of grace period): window and counts preserved. If current usage exceeds free limit, user sees "over free plan limit" until window naturally resets.

## Pricing

- **Tier:** free (default) + paid (£7.99/month GBP).
- **Product:** Matchbook subscription, monthly recurring.
- **Stripe setup:** one product + one price, created manually in the Stripe dashboard (test mode first, then live). Price ID lives in prod `.env` as `STRIPE_PRICE_ID`.

## Rough cost model (sanity check)

Model: `claude-sonnet-4-5` at ~$3 input / $15 output per MTok. Realistic heavy user (not theoretical max):

- **Free user burning the full allowance:** ~$1.40/mo in Anthropic costs. Acceptable acquisition cost.
- **Paid user doing a real search (10 jobs, 5 researches, ~100 drafts):** ~$5/mo cost. £7.99 minus Stripe fees leaves ~£4.50 margin.
- **Paid user maxing every cap:** ~$80/mo. Only achievable by scripted abuse; 10-per-kind-per-job cap (down from 20) keeps this bounded.

## Data model

### `users` — new columns

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `plan` | `varchar(20)` | no, default `'free'` | `'free' \| 'paid' \| 'paid_grandfathered'` |
| `stripe_customer_id` | `varchar(255)` | yes, unique | Populated on first Checkout create |
| `stripe_subscription_id` | `varchar(255)` | yes, unique | Populated on `checkout.session.completed` |
| `subscription_status` | `varchar(32)` | yes | Mirrors Stripe's status string — `active`, `past_due`, `canceled`, `incomplete_expired`, etc. |
| `subscription_current_period_end` | `timestamptz` | yes | Drives the grace-period cutoff |
| `cancel_at_period_end` | `boolean` | no, default `false` | So the UI can show "cancelling on <date>" |

### `usage_counters` — new table

```sql
CREATE TABLE usage_counters (
    id           uuid PRIMARY KEY,
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    resource     varchar(32) NOT NULL,
    scope_key    uuid NULL,
    window_start timestamptz NOT NULL,
    window_end   timestamptz NOT NULL,
    count        integer NOT NULL DEFAULT 0,
    UNIQUE (user_id, resource, scope_key, window_start)
);
CREATE INDEX ix_usage_counters_user_window ON usage_counters(user_id, window_start);
```

- `scope_key` is `NULL` for per-user resources, `job_id` for per-(user,job) resources.
- Old windows remain in the table as a historical record — handy for "you used 42 drafts last month" analytics. A future cron can prune rows older than N months if the table grows.
- Atomic UPSERT (`ON CONFLICT ... DO UPDATE ... SET count = count + 1 RETURNING count`) makes concurrent consume calls safe without application-level locks.

## Entitlement service

`backend/app/core/entitlements.py`:

```python
RESOURCES = {
    'jobs_created':         Resource(free=5,  paid=50, scope='user'),
    'company_research':     Resource(free=3,  paid=10, scope='user'),
    'draft_outreach':       Resource(free=3,  paid=10, scope='job'),
    'draft_form_response':  Resource(free=3,  paid=10, scope='job'),
    'draft_follow_up':      Resource(free=3,  paid=10, scope='job'),
    'draft_interview_prep': Resource(free=3,  paid=10, scope='job'),
    'cover_letter':         Resource(free=3,  paid=10, scope='job'),
    'ai_job_search':        Resource(free=1,  paid=5,  scope='user'),
}

def current_window(user: User, now: datetime) -> tuple[datetime, datetime]: ...
def plan_limit(user: User, resource: str) -> int | None:  # None == unlimited
async def remaining(db, user, resource, scope_key=None) -> int | None
async def consume(db, user, resource, scope_key=None) -> int  # raises 402 if over
async def refund(db, user, resource, scope_key=None) -> None
```

Behaviour:
- `paid_grandfathered` → `plan_limit()` returns `None` (unlimited); `consume` still writes the row for analytics but never raises.
- `consume` raises `HTTPException(status=402, detail={...})` when over, with fields `resource`, `limit`, `used`, `resets_at`, `upgrade_url`. The frontend uses these to render the upgrade CTA.
- `refund` decrements the count — used when the downstream AI call fails.

## FastAPI wiring

New dependency factory in `app/api/deps.py`:

```python
def entitlement(resource: str, scope: str = 'user'):
    async def _dep(
        user: User = Depends(get_verified_user),
        db: AsyncSession = Depends(get_db),
        job_id: UUID | None = None,  # resolved from path param by FastAPI
    ) -> None:
        scope_key = job_id if scope == 'job' else None
        await consume(db, user, resource, scope_key)
    return _dep
```

Applied to:

| Route | Dependency |
|---|---|
| `POST /jobs` (+ from-pdf, from-extension) | `entitlement('jobs_created')` |
| `POST /jobs/{id}/score` | *none — rescore is exempt* |
| `POST /jobs/{id}/company-research` | `entitlement('company_research')` |
| `POST /jobs/{id}/ai-outputs/outreach` | `entitlement('draft_outreach', 'job')` |
| `POST /jobs/{id}/ai-outputs/form-response` | `entitlement('draft_form_response', 'job')` |
| `POST /jobs/{id}/ai-outputs/follow-up` | `entitlement('draft_follow_up', 'job')` |
| `POST /jobs/{id}/ai-outputs/interview-prep` | `entitlement('draft_interview_prep', 'job')` |
| `POST /jobs/{id}/cover-letters` | `entitlement('cover_letter', 'job')` |

Entitlement consumption happens BEFORE the Anthropic call. If the AI call fails (timeout, 5xx, model refusal), the route refunds in its error path. Same transactional pattern as the registration-email fix in `auth.py` (noted in HANDOFF.md).

### Company research cache + quota

Current behaviour: `GET` returns cache (free, can be 404), `POST` always regenerates (expensive).

New behaviour for the spec:
- `GET /jobs/{id}/company-research` stays unchanged. Free cache read. Used by job detail page loads so an idle browse never burns a credit.
- `POST /jobs/{id}/company-research` is "I'm asking for research on this company". It:
    1. Consumes the `company_research` entitlement (raises 402 if over).
    2. Looks at the cache. If present **and not expired**, returns the cached briefing with `fresh=false`. No Anthropic spend.
    3. Otherwise generates via Claude + web search, upserts the cache, returns `fresh=true`.
    4. On downstream failure in (3), refunds the entitlement.

The quota charge represents the *action the user took*, not the server's cost. Users who research 3 popular companies get 3 cached responses for free to Matchbook but still use their 3 free credits — consistent with the pitch "3 researches/month". An explicit `?force=true` override to bypass the cache is **not** in scope here; let the 7-day TTL handle refresh.

## Billing routes

`backend/app/api/routes/billing.py`:

- `GET /billing/status` → `{plan, subscription_status, current_period_end, cancel_at_period_end, usage: {<resource>: {limit, used, remaining, resets_at}, ...}}`. Powers the UI. Includes per-job resources only in aggregate (totals across jobs) — per-job granularity is served by the job detail endpoint.
- `POST /billing/checkout` → creates a Stripe Checkout Session in subscription mode, sets `client_reference_id = user.id`, returns `{url}`. Reuses `stripe_customer_id` if already populated.
- `POST /billing/portal` → creates a Customer Portal session, returns `{url}`. Delegates cancel / card update / invoice history to Stripe.
- `POST /billing/webhook` → signature-verified via `stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)`. Idempotent by Stripe event ID (store processed IDs in Redis with a 24h TTL — re-delivery protection). Handles:
    - `checkout.session.completed` → set `plan='paid'`, save `stripe_subscription_id`.
    - `customer.subscription.updated` → sync `subscription_status`, `current_period_end`, `cancel_at_period_end`.
    - `customer.subscription.deleted` → set `plan='free'`, clear subscription fields (keep `stripe_customer_id` so they can resubscribe cleanly).
    - `invoice.payment_failed` → do nothing to `plan`; Stripe's smart retries handle it. When the subscription eventually enters `incomplete_expired` or `canceled`, the `subscription.deleted` handler drops the plan.

The webhook is the single source of truth. The Checkout success page renders "Thanks, activating your plan" and polls `GET /billing/status` — it does not mutate the plan directly.

Per-job quota data is served by extending existing job detail GETs with a `quota` block:

```
GET /jobs/{id}
  -> { ..., quota: {
        draft_outreach:       {limit:3, used:1, remaining:2, resets_at:...},
        draft_form_response:  {...}, ...
        cover_letter:         {...}
      } }
```

Avoids the frontend making N+1 calls to check quota per button.

## Frontend

- **Job detail page:** each generate button gains a caption — `"2 drafts left this month"`. At 0 remaining, button text becomes `"Upgrade to continue"`, disabled state swaps for an `<a>` to `/billing`. Reads from the `quota` block on `GET /jobs/{id}`.
- **Dashboard header:** small pill `"3/5 jobs this month"`. At ≥80% it turns rust-coloured (Warm Modern palette — `mb-accent-rust` token). Reads from `GET /billing/status`.
- **Billing page (new, `/billing`):** current plan card, usage table, Upgrade button (Free → Checkout) or Manage button (Paid → Portal), support link.
- **402 Payment Required handler:** the frontend API client intercepts 402, shows a toast with upgrade CTA, and links to `/billing`. Avoids per-route boilerplate.
- After a successful generation, the frontend optimistically decrements the quota shown and re-fetches on next page load. No polling.

## Rollout

1. **Alembic migration** adds user columns + `usage_counters` table + default `plan='free'` for all existing users + sets `plan='paid_grandfathered'` on `email='thomashughes1992.th@gmail.com'`.
2. **`.env` additions on prod first** (per handoff rule): `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID`, `BILLING_SUCCESS_URL`, `BILLING_CANCEL_URL`. `backend/app/core/config.py` gets matching Pydantic settings. Prod edit → push → auto-deploy.
3. **Stripe setup:** product + £7.99/mo GBP recurring price created in test mode; webhook endpoint registered pointing at `https://matchbook.tag-art.co.uk/api/v1/billing/webhook`; after test-mode end-to-end passes, same in live mode.
4. **No historical backfill.** Every existing user starts at 0 in their current window. The handoff notes 1 real user (Thomas, already grandfathered) and 8 jobs already in prod — grandfathering handles that case; no other users exist yet.

## Risks and mitigations

1. **Webhook retries.** Stripe redelivers events; the webhook must be idempotent. Mitigation: store processed `event.id` in Redis with 24h TTL, short-circuit duplicates with a 200.
2. **Webhook signature verification.** Missing or wrong `STRIPE_WEBHOOK_SECRET` → signature fails → 400 → Stripe retries → we never upgrade anyone. Mitigation: explicit startup check that the env var is set; test-mode webhook exercise before going live.
3. **Apache body limit.** `/var/www/.../vhost_ssl.conf` has `LimitRequestBody 20M` (per handoff). Stripe webhooks are <10K — fine. No change needed.
4. **Consume-then-fail leakage.** If the Anthropic call raises but the refund also raises (rare — DB connection lost), the user loses one credit. Bounded; acceptable; not worth a 2PC.
5. **Short-month anchor.** Signup on Jan 31 → Feb has no 31. Resolution: clamp to last day of month.
6. **Cache hits counting toward `company_research`.** Per decision — caller pays in quota even if the server doesn't pay in API cost. Surfaced in user docs: "company research uses one credit whether it's fresh or cached."
7. **Grandfathered account loses grandfather.** If Thomas's email ever changes, the override evaporates. Mitigation: grandfathered status keyed on user_id in a follow-up migration if account churn ever happens. Not in this work.
8. **Re-registration to reset free allowance.** Blocked by existing UNIQUE email constraint. Different emails are trivial to obtain, but that's true of any free-tier product — accepted.
9. **Prod `.env` drift.** Any missed env var on prod before the deploy → backend crash-loops on startup. Mitigation: the handoff rule applies — edit prod `.env` first, push second.
10. **Stripe test vs live keys.** Shipping test keys to prod = Checkout opens but no real money flows. Mitigation: obvious, but documented as a deploy checklist item.
11. **GDPR / deletion.** User deletion cascades to `usage_counters` via FK. Stripe customer records are NOT deleted — manual ops procedure documented: if a deleted user's data needs to be purged from Stripe too, hit the Stripe API by `stripe_customer_id` before the DB delete.
12. **Refund window race.** Two concurrent consumes + one fail = correct final count (both INCR-atomic; refund is -1 atomic). Crash between consume and refund leaks a credit but bounded to one per crash.

## Testing

- Unit: `current_window` for 1st, 15th, 31st anchors across Jan/Feb/leap-year.
- Unit: `consume` / `refund` concurrency test — N parallel consumes on a fresh counter give exactly N.
- Integration: free user hits cap on each resource → 402 with correct body.
- Integration: upgrade preserves window + usage; downgrade preserves; consumption after downgrade respects free limits.
- Integration: grandfathered user — 100 consume calls, never raises, counter still writes.
- Webhook: Stripe CLI replay of `checkout.session.completed`, `subscription.updated` (cancel_at_period_end), `subscription.deleted`. Idempotency: double-deliver → no double upgrade.
- E2E (manual): test-mode Checkout, status flips, UI shows updated remaining.

## Commit order for the implementation plan

The implementation plan (follow-up doc) will break this into commits sized to review individually. Rough shape:
1. Alembic migration + `entitlements.py` + tests
2. Dependency + apply to existing routes + tests + error handler
3. Job detail quota block + frontend quota display on buttons
4. Billing routes (status, checkout, portal)
5. Stripe webhook handler + config + idempotency
6. Frontend `/billing` page + 402 toast
7. Rollout: prod `.env`, Stripe dashboard setup, grandfather migration verified

## Open questions / assumptions to verify

- **Your email for grandfathering:** `thomashughes1992.th@gmail.com` (confirmed 2026-04-20). Memory's `userEmail` is a different address — the grandfathering migration uses the Matchbook account email specifically.
- The webhook endpoint path: `/api/v1/billing/webhook`. Stripe will need the full public URL; plan assumes Apache + nginx already route `/api/` correctly to the FastAPI app.
- Stripe **test-mode first** is assumed for at least the initial deployment; live keys swapped in once a full Checkout → upgrade → cancel → downgrade cycle passes on the prod domain.
