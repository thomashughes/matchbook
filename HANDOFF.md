# Matchbook v2 — handoff

**Timestamp:** 2026-04-20 (continuing 2026-04-19 deployment + Phase 3 work)
**Branch:** `main` (deploys from here via GH Actions).
**Status:** Freemium caps + Stripe scaffolding shipped to prod. Billing routes live but Stripe is NOT wired yet — `/billing/checkout` returns 503 until the Stripe dashboard is set up and prod `.env` gets the three `STRIPE_*` vars. **Free-tier usage caps are enforced today.**

Read the repo `CLAUDE.md` first for local dev commands. Run docker/compose yourself — never ask the user to paste output.

## What's live

- `https://matchbook.tag-art.co.uk` — Matchbook v2 SPA + API. Apache reverse-proxies to frontend container on `127.0.0.1:3085`; container nginx proxies `/api/` to backend on port 8000 internal.
- `https://matchbookv1.tag-art.co.uk` — old Node/Express v1, kept live on port 3080 via ProxyPass. Data untouched.
- Containers on VPS (`docker compose ps` in `/opt/matchbookv2`):
    - `matchbookv2-backend-1` → 3086 (FastAPI, migrations auto-run on start)
    - `matchbookv2-frontend-1` → 3085
    - `matchbookv2-postgres-1` → internal only
    - `matchbookv2-redis-1` → internal only
- 3 real users in prod:
    - `thomashughes1992.th@gmail.com` — `paid_grandfathered` (unlimited)
    - `tagriffinphotography@gmail.com` — `free` (capped at 5 jobs / 3 research / 3 drafts per kind per job, per month)
    - `awillis@antillion.com` — `free` (same caps)
  If Thomas wants `tagriffinphotography@gmail.com` unlimited too, one SQL update: `UPDATE users SET plan='paid_grandfathered' WHERE email='tagriffinphotography@gmail.com';` on the prod Postgres.

## How deploys work

Push to `main` → GitHub Actions (`.github/workflows/deploy.yml`) → SSH to server → `git reset --hard origin/main` + `docker compose up -d --build` + healthz + public smoke test. ~20-25s end-to-end.

Any change touching `.env` schema (new key, renamed key) needs the prod `.env` updated BEFORE the deploy runs, or the backend container will crash on startup. Edit `/opt/matchbookv2/.env` on server first, push second.

## Critical server locations

- `/opt/matchbookv2/.env` — prod env (mode 600, thughes:docker). Holds DB password, Fernet, Anthropic key, SMTP password, JWT paths, and now the five billing vars (see below).
- `/opt/matchbookv2/backend/keys/jwt_{private,public}.pem` — RS256 keypair for prod (distinct from dev).
- `/var/www/vhosts/system/matchbook.tag-art.co.uk/conf/vhost_ssl.conf` — Apache customisation (reverse proxy to 3085, LE .well-known exclusion, 20MB LimitRequestBody, ProxyTimeout 300s).
- `/var/log/maillog` — postfix delivery log (on host, not container).

## Freemium + Stripe work — what shipped 2026-04-20

### The entitlement system (works today, Stripe-independent)

- **Spec:** `docs/superpowers/specs/2026-04-20-freemium-limits-stripe-design.md`. Read it if you need context on design decisions — the matrix, the signup-anniversary window, the "cache-hit still costs a credit" rule, the risks list.
- **Data model:**
    - `users` gained `plan` (`'free' | 'paid' | 'paid_grandfathered'`), `stripe_customer_id`, `stripe_subscription_id`, `subscription_status`, `subscription_current_period_end`, `cancel_at_period_end`.
    - New `usage_counters` table, one row per `(user_id, resource, scope_key, window_start)`. Upsert-driven atomic increments.
    - Migration: `backend/alembic/versions/20260420_1000_billing_entitlements.py`. Grandfathers `thomashughes1992.th@gmail.com` in the same revision.
- **Core module:** `backend/app/core/entitlements.py` — `RESOURCES` registry, `current_window()` (clamps Jan 31 → Feb 28), `consume()`, `refund()`, `QuotaExceeded` (HTTP 402).
- **Dep factory:** `app/api/deps.py:entitlement(resource, scope)` used as `dependencies=[Depends(entitlement("draft_outreach", "job"))]` on every paid AI route.
- **Refund-on-failure pattern:** every AI route wraps its body in `try/except` and calls `refund(...)` on exception. Same transactional contract as the `auth.py` register-email fix.
- **Company research tweak:** `POST /jobs/{id}/company-research` now serves cache without regenerating when fresh, but still consumes one credit. `GET` stays free (passive page loads must not burn credits). This matches the "3 researches/month" marketing pitch.
- **Job detail response:** `GET /jobs/{id}` now includes a `quota` array with `QuotaItem` per per-job resource (`draft_*`, `cover_letter`). The frontend consumes this for the "2 drafts left" captions.

### Billing routes (all live; `/checkout` and `/portal` return 503 until Stripe is configured)

- `GET /api/v1/billing/status` — plan, subscription fields, per-user usage list. Works today, no Stripe required.
- `POST /api/v1/billing/checkout` — returns Stripe Checkout URL. **Today: 503 "Billing not configured"** because `STRIPE_SECRET_KEY` is empty in prod.
- `POST /api/v1/billing/portal` — returns Stripe Customer Portal URL. Same 503 situation.
- `POST /api/v1/billing/webhook` — signature-verified, idempotent via Redis `SET NX EX`. Handles `checkout.session.completed`, `customer.subscription.{created,updated,deleted}`, `invoice.payment_failed`. Currently 503 because `STRIPE_WEBHOOK_SECRET` is empty.

### Frontend

- New page `frontend/src/pages/BillingPage.tsx` at `/billing`. Plan card, Upgrade/Manage buttons, usage table.
- `frontend/src/components/layout/UsagePill.tsx` in the top bar — shows `X/5 jobs · Y/3 research`, rust-coloured at ≥80%, flat "Unlimited" for grandfathered accounts.
- `frontend/src/components/jobs/QuotaCaption.tsx` under every per-job generate button (cover letter, outreach, form response, follow-up, interview prep). Reads from `JobDetail.quota`. At 0 remaining becomes "No X left this month — upgrade to continue" link to `/billing`.
- `frontend/src/components/jobs/UserQuotaCaption.tsx` under the company-research generate button. Reads from `/billing/status`.
- `frontend/src/api/client.ts` — the API wrapper now preserves structured 402 detail on `ApiError.data`. Use `isQuotaError(err)` to narrow.

## What's needed tomorrow — Stripe integration steps

Do these in order. Don't push code changes between steps unless a step explicitly says to.

### 1. Stripe dashboard setup (test mode first)

1. Sign in to Stripe dashboard (or create an account if needed). Flip the top-left toggle to **Test mode**.
2. Products → Create product "Matchbook". Add recurring price: **£7.99 GBP, monthly**. Save the **price ID** (`price_...`).
3. Developers → Webhooks → Add endpoint:
    - URL: `https://matchbook.tag-art.co.uk/api/v1/billing/webhook`
    - Events: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`.
    - After save, reveal the **Signing secret** (`whsec_...`).
4. Developers → API keys → copy the **Secret key** (`sk_test_...`).

### 2. Write to prod `.env` FIRST (before any push)

SSH to the server:

```bash
ssh root@tag-art.co.uk
nano /opt/matchbookv2/.env
```

Append these five lines (replace values with the ones from step 1):

```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
BILLING_SUCCESS_URL=https://matchbook.tag-art.co.uk/billing?status=success
BILLING_CANCEL_URL=https://matchbook.tag-art.co.uk/billing?status=cancel
```

Restart so the new env is picked up:

```bash
cd /opt/matchbookv2 && docker compose up -d --build backend
docker compose logs --tail=30 backend
```

Backend should come up cleanly. `GET /api/v1/billing/status` still works (already did).

### 3. End-to-end test in test mode

From the live site (as `tagriffinphotography@gmail.com` or a fresh test account):

1. Visit `/billing`. Should show plan=Free and usage table.
2. Click "Upgrade to Paid". Should redirect to `checkout.stripe.com`.
3. Use a Stripe test card: `4242 4242 4242 4242`, any future date, any CVC.
4. Complete payment. Stripe redirects back to `/billing?status=success`.
5. `docker compose logs backend` on the server — should see the webhook fire:
    - `checkout.session.completed` → plan flipped to `paid`.
    - `customer.subscription.created` → `subscription_status=active`, `current_period_end` populated.
6. Reload `/billing`. Plan should now show "Paid — £7.99/month" and the button should say "Manage subscription".
7. Click "Manage subscription" → opens Stripe Customer Portal.
8. Cancel the subscription there. `cancel_at_period_end` flips to true. The `/billing` page shows "Your subscription ends <date>".
9. (Optional — only if you want to confirm the downgrade path.) From Stripe dashboard, immediately delete the subscription. Webhook fires `subscription.deleted`; plan flips back to `free`.

If any of those fail, tail backend logs and check the Stripe dashboard webhook delivery log for the signature / event id.

### 4. Flip to live mode

Once the test-mode flow is green:

1. In Stripe dashboard, top-left toggle → **Live mode**.
2. Repeat steps 1.2 and 1.3 above (product + webhook) in live mode. New secrets.
3. SSH to server, swap the three `STRIPE_*` env vars in `/opt/matchbookv2/.env` for the live values.
4. `docker compose up -d --build backend`.
5. Done.

## UX wart to be aware of until step 2 is done

While `STRIPE_SECRET_KEY` is empty on prod:

- The `/billing` page shows an "Upgrade to Paid" button that, when clicked, returns 503 and the UI shows "Something went wrong reaching Stripe."
- A 5-minute polish if you want to kill the wart before tomorrow: add `stripe_configured: bool` to the `BillingStatusOut` payload (returns `bool(settings.STRIPE_SECRET_KEY)`), and have the frontend hide the Upgrade button + show "Upgrade coming soon" when false. The scaffolding to do this is trivial; skip it if you're rolling out Stripe within 24h.

## Known edges / next steps

- **Phase 3 panels still not user-verified in prod:** form_response, follow_up, interview_prep, company_research. Routes + prompts + panels exist from prior sessions; no end-to-end smoke against a real JD yet post-deploy. The company-research POST was refactored this session — its cache-hit + credit-consume path has unit logic that hasn't been user-exercised.
- **AI job search is scaffolded, not shipped.** The `ai_job_search` resource is registered in `RESOURCES` with 1/free, 5/paid caps. The counter column already exists. When building the feature: one `Depends(entitlement("ai_job_search"))` on the new POST route is all the quota wiring needed.
- **Resend-verification endpoint still missing.** Low-cost follow-up: `POST /auth/resend-verification` keyed by email, rate-limited.
- **No "over-limit freeze" UX.** Buttons don't disable at 0 remaining — clicking generates → 402 → toast. Cheap polish: each panel checks `quota.find(...)?.remaining === 0` and disables its button.
- **`paid_grandfathered` is keyed on email in the migration.** If Thomas changes email, the override is lost. Not in scope here; easy fix if it ever matters: migrate to key on user_id.
- **Refund race.** A process crash between `consume()` and `refund()` leaks one credit. Bounded and acceptable — don't "fix" with a 2PC.

## Architectural decisions worth preserving

- **Entitlements (Postgres) vs burst limits (Redis) stay separate.** They protect against different threats: cost-runaway vs DDoS. Don't collapse them.
- **Webhook is authoritative, success redirect is not.** The `/billing?status=success` page is just a thanks page and polls `/billing/status`. Never mutate plan state from a user-facing redirect handler.
- **Customer lazy creation.** Stripe customer row is created on first Checkout, not at signup. Keeps the Stripe dashboard clean of free users who never upgrade.
- **`plan` column is authoritative for entitlements.** `subscription_status` is informational only — use it for UI copy, not for quota decisions.
- **Refund-on-failure pattern mirrors register-email transactional rule.** If you add a new step that touches paid compute, wrap it: consume → try Anthropic → on exception `refund(...)` → re-raise.
- **Register = transactional-for-email.** If you add any future steps to signup (create default workspace, seed data, etc.), decide explicitly whether they're part of the "success criterion" or best-effort; wrap in the same try/delete/raise pattern if they are.

## How to resume

1. `cd /Users/thomashughes/Desktop/Projects/matchbookv2`
2. `docker compose ps` — confirm all four Up locally.
3. Pick a direction:
    - **Finish Stripe integration** — follow the "What's needed tomorrow" section above.
    - **Kill the UX wart** — 5-min polish to hide the Upgrade button while Stripe is unconfigured.
    - **Harden quota UX** — disable generate buttons at 0 remaining.
    - **Verify Phase 3 panels end-to-end** in prod with a real JD.
    - **Pick up AI job search** — the quota slot is already registered; build the route + panel.

## Commands you'll use

- Backend change + deploy: `git push` → Actions does the rest. Local debug: `docker compose up -d --build backend`.
- Frontend change: `docker compose up -d --build frontend` locally; push to deploy.
- Migration: create with `docker compose exec backend alembic revision -m "..."`, commit, push. Container re-runs `alembic upgrade head` on start.
- Check deploy: `gh run list --workflow=deploy.yml --limit 5`.
- Inspect prod DB: `ssh root@tag-art.co.uk 'cd /opt/matchbookv2 && docker compose exec -T postgres psql -U matchbook -d matchbook -c "SELECT … "'`.
- Tail prod backend: `ssh root@tag-art.co.uk 'cd /opt/matchbookv2 && docker compose logs -f --tail=100 backend'`.
- Prod usage debug (active windows for one user): `SELECT resource, scope_key, window_start, window_end, count FROM usage_counters WHERE user_id = (SELECT id FROM users WHERE email = '...') ORDER BY window_start DESC;`

## Rules carried over

- Every non-trivial function/decision gets a WHAT + WHY comment. Portfolio-graded.
- Warm Modern tokens only via `mb-*` utility classes in `globals.css`. RAG ring via `scoreColour()`.
- No tokens in localStorage. Access = Zustand-in-memory, refresh = httpOnly cookie path-scoped to `/auth`.
- `/jobs/compare` must stay declared **before** `/jobs/{job_id}` in `routes/jobs.py`.
- Job list endpoint uses a batched latest-scores fetch — don't reintroduce N+1.
- `/jobs/{id}/ai-outputs/{output_id}` DELETE must stay under the generic router for all future kinds.
- Version cards: only latest auto-opens; copy with Check confirmation; delete with confirm UX where destructive.
- **Never commit `.env` or `backend/keys/*.pem`.** They're gitignored — don't add exceptions.
- **Never add `STRIPE_*` vars to the committed `.env.example` with real values** — the example has placeholders only. Real secrets live only in `/opt/matchbookv2/.env` on the server and in local dev machines.
