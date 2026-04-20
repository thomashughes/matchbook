"""
Billing routes — status, Checkout, Customer Portal, webhook.

Architecture:
    - POST /billing/checkout  : create a Stripe Checkout Session, return
                                its URL. Frontend redirects the browser.
    - POST /billing/portal    : create a Customer Portal session. Used
                                for cancel / update-card / view-invoices.
                                We outsource all that UI to Stripe.
    - POST /billing/webhook   : Stripe posts subscription events here.
                                Signature verified, event dispatched.
                                This is the single source of truth for
                                plan state — NOT the success redirect.
    - GET  /billing/status    : snapshot of plan + usage for the UI.

Why the webhook is authoritative:
    The success redirect is just a thanks page. A malicious user could
    craft a request to it, and it doesn't prove Stripe actually charged
    them. The webhook is signed by Stripe's secret + delivered on their
    infra retries. Only it should mutate plan state.

Idempotency:
    Stripe may redeliver an event (retries on non-2xx, or just because).
    We store processed event IDs in Redis with a 24h TTL and short-
    circuit duplicates with 200. Missing a second delivery is fine;
    processing the same upgrade twice is also fine (idempotent writes)
    but we still dedupe to save work.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.entitlements import RESOURCES, current_window, plan_limit
from app.core.rate_limit import get_redis
from app.core.stripe_client import get_stripe
from app.models.usage_counter import UsageCounter
from app.models.user import User
from app.schemas.billing import (
    BillingStatusOut,
    CheckoutOut,
    PortalOut,
    UsageItem,
)

router = APIRouter(prefix="/billing", tags=["billing"])

settings = get_settings()


# --- helpers --------------------------------------------------------------


async def _ensure_stripe_customer(user: User, db: AsyncSession) -> str:
    """Return the user's Stripe customer id, creating one on first use.

    Why create the customer lazily rather than at signup:
        Most users never upgrade. A free user doesn't need a Stripe
        customer record and every created customer is a row in Stripe's
        dashboard someone might later have to clean up.
    """
    if user.stripe_customer_id:
        return user.stripe_customer_id

    s = get_stripe()
    customer = s.Customer.create(
        email=user.email,
        # client_reference / metadata linking back to our user_id so
        # support staff in the Stripe dashboard can find the account
        # this customer relates to without an email lookup.
        metadata={"matchbook_user_id": str(user.id)},
    )
    user.stripe_customer_id = customer.id
    await db.commit()
    return customer.id


async def _build_usage(user: User, db: AsyncSession) -> list[UsageItem]:
    """Compute the per-resource UsageItem list for BillingStatusOut.

    Only scope='user' resources are included — per-job resources would
    inflate this list by #jobs × 5 kinds and are better served inline
    with the job detail response.
    """
    start, end = current_window(user)

    # Fetch all counter rows for the current window in one query.
    # Matching on window_start (=) is exact and uses the unique index.
    rows = (
        await db.execute(
            select(
                UsageCounter.resource,
                UsageCounter.count,
            ).where(
                UsageCounter.user_id == user.id,
                UsageCounter.window_start == start,
                UsageCounter.scope_key.is_(None),
            )
        )
    ).all()
    by_resource: dict[str, int] = {r: int(c) for r, c in rows}

    items: list[UsageItem] = []
    for key, spec in RESOURCES.items():
        if spec.scope != "user":
            continue
        used = by_resource.get(key, 0)
        limit = plan_limit(user, key)
        items.append(
            UsageItem(
                resource=key,
                limit=limit,
                used=used,
                remaining=(None if limit is None else max(limit - used, 0)),
                resets_at=end,
            )
        )
    return items


# --- status ---------------------------------------------------------------


@router.get("/status", response_model=BillingStatusOut)
async def billing_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BillingStatusOut:
    """Snapshot used by the dashboard pill and the /billing page.

    get_current_user (not get_verified_user): unverified users can
    still see their plan state — useful if verification is pending
    and they want to know the billing side is fine.
    """
    usage = await _build_usage(user, db)
    return BillingStatusOut(
        plan=user.plan,
        subscription_status=user.subscription_status,
        current_period_end=user.subscription_current_period_end,
        cancel_at_period_end=user.cancel_at_period_end,
        usage=usage,
    )


# --- checkout -------------------------------------------------------------


@router.post("/checkout", response_model=CheckoutOut)
async def create_checkout_session(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutOut:
    """Start a Stripe Checkout session for the £7.99/mo subscription.

    Already-paid users get a 400 — there's no "add another subscription";
    they should use the Customer Portal to manage the one they have.
    Grandfathered users get a 400 for the same reason (they're already
    past the paywall).
    """
    if user.plan in ("paid", "paid_grandfathered"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="You already have access to paid features.",
        )

    if not settings.STRIPE_PRICE_ID:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing price is not configured on this environment.",
        )

    s = get_stripe()
    customer_id = await _ensure_stripe_customer(user, db)

    session = s.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": settings.STRIPE_PRICE_ID, "quantity": 1}],
        success_url=settings.BILLING_SUCCESS_URL,
        cancel_url=settings.BILLING_CANCEL_URL,
        # client_reference_id echoes through to the webhook so even if
        # customer metadata is stripped (Stripe occasionally trims
        # legacy fields on older events) we can still map the event to
        # our user.
        client_reference_id=str(user.id),
        # Suppress the promo-code input by default — we don't run promos
        # yet. Flip to True once marketing wants them.
        allow_promotion_codes=False,
    )
    return CheckoutOut(url=session.url)


# --- portal ---------------------------------------------------------------


@router.post("/portal", response_model=PortalOut)
async def create_portal_session(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortalOut:
    """Open the Stripe Customer Portal.

    Requires an existing Stripe customer — i.e. the user has at least
    attempted Checkout. Free users who never checked out get a 400.
    """
    if not user.stripe_customer_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="No billing account exists yet. Start a subscription first.",
        )

    s = get_stripe()
    portal = s.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=settings.BILLING_SUCCESS_URL,
    )
    return PortalOut(url=portal.url)


# --- webhook --------------------------------------------------------------


# Redis TTL for "event has been processed" dedupe keys. 24h is enough
# to cover Stripe's retry window with headroom.
WEBHOOK_DEDUPE_TTL = 60 * 60 * 24


async def _already_processed(event_id: str) -> bool:
    """Check-and-set against Redis for webhook idempotency.

    Returns True if this event id has already been seen. Uses SET NX
    to make the check atomic with the mark-as-seen write.
    """
    r = get_redis()
    # NX = only set if key doesn't exist. Returns truthy on first set,
    # falsy if the key already existed — meaning we've seen this event.
    was_set = await r.set(
        f"stripe:event:{event_id}",
        "1",
        ex=WEBHOOK_DEDUPE_TTL,
        nx=True,
    )
    return not bool(was_set)


async def _get_user_by_customer(
    customer_id: str, db: AsyncSession
) -> User | None:
    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    return result.scalar_one_or_none()


async def _get_user_for_event(
    obj: dict[str, Any], db: AsyncSession
) -> User | None:
    """Resolve the User this event relates to.

    Tries in order:
      1. `customer` field on the object (present on subscription / invoice
         events).
      2. `client_reference_id` (present on checkout.session.* events —
         pulls user.id directly and avoids a round trip via customer).
    """
    customer_id = obj.get("customer")
    if customer_id:
        user = await _get_user_by_customer(customer_id, db)
        if user is not None:
            return user

    ref = obj.get("client_reference_id")
    if ref:
        result = await db.execute(select(User).where(User.id == ref))
        return result.scalar_one_or_none()

    return None


def _period_end(sub: dict[str, Any]) -> datetime | None:
    """Extract current_period_end from a subscription object, UTC-aware."""
    ts = sub.get("current_period_end")
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc)


async def _apply_subscription(
    user: User, sub: dict[str, Any], db: AsyncSession
) -> None:
    """Sync a user row from a Stripe subscription object.

    Rules:
        - Any status other than 'canceled' / 'incomplete_expired' ⇒
          keep or promote to plan='paid' (unless grandfathered; those
          are untouched by webhooks).
        - 'canceled' or 'incomplete_expired' ⇒ plan='free' and clear
          subscription_id. This is the subscription.deleted path in
          practice.
        - Always mirror status + period_end + cancel_at_period_end.
    """
    # Never touch a grandfathered account via the webhook. The admin
    # override outlives any billing state.
    if user.plan == "paid_grandfathered":
        return

    status_str = sub.get("status")
    user.subscription_status = status_str
    user.subscription_current_period_end = _period_end(sub)
    user.cancel_at_period_end = bool(sub.get("cancel_at_period_end"))

    if status_str in (None, "canceled", "incomplete_expired"):
        user.plan = "free"
        user.stripe_subscription_id = None
    else:
        user.plan = "paid"
        user.stripe_subscription_id = sub.get("id")


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Handle Stripe subscription lifecycle events.

    This endpoint is NOT protected by get_current_user — Stripe hits
    it directly without our JWT. Authenticity comes from the
    Stripe-Signature header verified against STRIPE_WEBHOOK_SECRET.
    A missing or invalid signature → 400. We do NOT log the raw
    payload on invalid signatures (potential sensitive data).
    """
    if not settings.STRIPE_WEBHOOK_SECRET:
        # Fail closed — no secret set means we can't verify anything
        # and the webhook must not silently accept traffic.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook secret not configured.",
        )

    s = get_stripe()
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = s.Webhook.construct_event(
            payload, sig, settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception:
        # Invalid signature or malformed payload. Do NOT 500 — Stripe
        # would retry forever. 400 tells Stripe "this event will never
        # succeed here, stop retrying".
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature.",
        )

    event_id = event.get("id")
    if event_id and await _already_processed(event_id):
        # Already handled a previous delivery — return 200 so Stripe
        # stops retrying. Not 204 because the stripe-python examples
        # all use 200 and that's the least surprising for operators
        # reading the Stripe dashboard delivery log.
        return Response(status_code=status.HTTP_200_OK)

    etype = event.get("type", "")
    data_obj: dict[str, Any] = event.get("data", {}).get("object", {}) or {}

    user = await _get_user_for_event(data_obj, db)

    if etype == "checkout.session.completed":
        # The session object itself doesn't carry current_period_end —
        # we have to fetch the subscription it created.
        sub_id = data_obj.get("subscription")
        if user is not None and sub_id:
            sub = s.Subscription.retrieve(sub_id)
            # The SDK returns a stripe.Subscription which supports
            # .get(); coerce to dict-like via model_dump when available
            # but .get() works on the SDK object directly so we pass
            # it as-is.
            await _apply_subscription(user, sub, db)
            await db.commit()

    elif etype in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        if user is not None:
            await _apply_subscription(user, data_obj, db)
            await db.commit()

    elif etype == "invoice.payment_failed":
        # Don't immediately downgrade — Stripe's smart retries might
        # still succeed. subscription.status is the signal to act on,
        # and it will flow through customer.subscription.updated when
        # it changes. We do nothing here except log implicitly via
        # the dedupe key.
        pass

    # Ignore everything else. Stripe sends a lot of events; we only
    # care about the handful above.

    return Response(status_code=status.HTTP_200_OK)
