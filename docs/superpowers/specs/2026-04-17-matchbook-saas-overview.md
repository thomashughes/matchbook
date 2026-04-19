# Matchbook SaaS — roadmap overview

**Date:** 2026-04-17
**Status:** Direction agreed with user. Each sub-project gets its own
spec + plan before implementation. This doc is the index.

## Product shape

Matchbook becomes a freemium SaaS job-hunt copilot. Two features are
metered because they cost real money to run (Anthropic + web_search);
the rest of the app stays free. Chrome extension adds free ingestion
from LinkedIn.

## Pricing

| Tier      | Price      | Company research | Claude job search | Notes |
| --------- | ---------- | ---------------- | ----------------- | ----- |
| Free      | £0         | 3 lifetime       | 3 lifetime        | Counts all-time usage, not monthly. If you upgrade then downgrade, your free allowance is already spent. |
| Pro       | £6.99/mo   | 10 per month     | 10 per month      | Anniversary-based reset. |
| Unlimited | £19.99/mo  | 100 per month*   | 100 per month*    | *Fair-use cap — protects the API budget against abuse. Not shown on the pricing page. |

Billing cycle: monthly only (annual deferred — avoids refund headaches
while we validate product–market fit).

Cancellation: anytime via Stripe portal. Access continues until
period end. No pro-rata refunds.

### Unit economics (for sanity)

- Company research generation: ~$0.06, but shared cache means blended
  cost per lookup drops toward ~$0.03 as the user base grows.
- Claude job search: ~$0.17 per run (more searches, larger output, no
  meaningful cache — every user's criteria differ).
- Pro worst case cost: 10 × $0.03 + 10 × $0.17 = ~$2.00/month. Revenue
  after Stripe ≈ £5.90. Margin ≈ £4.00.
- Unlimited worst case cost at 100+100: ~$20/month. Revenue after
  Stripe ≈ £19.20. The 100 fair-use cap exists to keep this from
  going negative.

## Sub-projects (build order)

Each is shippable on its own. Don't start N+1 until N is deployed.

1. **Entitlement foundation** (`A`) — DB migration, middleware, 402
   contract. No UI. Everyone becomes `free` on migration.
2. **Chrome extension** (`B`) — Manifest v3, scrapes LinkedIn DOM,
   POSTs to `/jobs/from-extension` authenticated by a Personal Access
   Token. Free forever. No entitlement gate (ingestion is free; the
   features it feeds *into* are where cost lives).
3. **Billing & quota UI** (`C`) — Stripe Checkout, webhook, account
   page showing quota, upgrade CTA. First revenue.
4. **Claude job search** (`D`) — new feature, gated on day one.
   Preview cards; user saves individually into their jobs list.
5. **Legal + deploy** (`E`) — Terms, Privacy, Cookie banner, GDPR
   delete endpoint, Plesk vhost, production `.env`, first live
   launch.

## Interfaces between sub-projects

Agreeing these up front prevents rework:

### Entitlement middleware (from A)

Two async helpers used by C and D:

```python
async def check_quota(user: User, feature: Feature, db: AsyncSession) -> None:
    """Raise 402 HTTPException if the user has exhausted their allowance."""

async def record_usage(user: User, feature: Feature, db: AsyncSession) -> None:
    """Insert a feature_usage row. Call AFTER the paid operation succeeds."""
```

`Feature` is a `Literal["company_research", "job_search"]`.

### 402 response shape (consumed by C's frontend)

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

The frontend's `ApiError` already carries `detail`; we just need to
JSON-parse it when status === 402.

### Jobs table (consumed by D)

Already has `source_type` — add `"search"` to the `Literal`. Nothing
else changes. Job rows from a Claude-generated search behave like any
other job once saved.

### Personal access tokens (introduced by B, reused elsewhere)

One-off tokens the extension uses instead of refresh cookies (cookies
don't cross origins cleanly). Same model can later back a "public API"
tier if we ever want one.

## What we're explicitly NOT building now

- Annual billing. Deferred until churn data warrants it.
- Team / org accounts. Out of scope for v1 — adds role model complexity.
- Social login. Email+password is enough; adds no revenue.
- Public marketing site. The `/login` page doubles as the landing
  page until we see traction worth investing in copywriting.
- OCR for image-scanned PDFs. Already not supported; out of scope.
- Custom domains for tenants. One URL: matchbook.tag-art.co.uk.

## Open questions deferred to each sub-project

- Extension: which LinkedIn DOM nodes? How do we handle LinkedIn's
  SPA navigation? (B's spec.)
- Stripe: products + prices set up via dashboard or code? (C's spec.)
- Job search: prompt shape, search diversity controls? (D's spec.)
- Deploy: does Plesk SMTP work on port 587 from inside a Docker
  container? (E's spec — worth testing early.)
