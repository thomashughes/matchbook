"""
Stripe SDK wrapper.

The `stripe` module is process-global: setting stripe.api_key once
affects every subsequent call in the process. That's how the SDK is
designed; we just wrap it in a module that makes the initialisation
explicit and auditable.

Why a wrapper rather than sprinkling stripe.api_key= through the app:
    - Tests can monkeypatch `get_stripe()` to return a stub module
      without touching env vars.
    - If Stripe is not configured (empty STRIPE_SECRET_KEY — local dev),
      we raise a clear HTTP 503 from billing routes instead of letting
      a confusing AuthError from the SDK bubble up.
    - Centralises the "is billing available?" check for health probes.
"""

from __future__ import annotations

import stripe
from fastapi import HTTPException, status

from app.core.config import get_settings

_configured = False


def _configure_once() -> None:
    """Initialise stripe.api_key on first use. Idempotent."""
    global _configured
    if _configured:
        return
    settings = get_settings()
    if not settings.STRIPE_SECRET_KEY:
        # Don't raise here — some environments (local dev, CI) run the
        # app without Stripe. We raise only when a billing route is
        # actually called.
        return
    stripe.api_key = settings.STRIPE_SECRET_KEY
    # Pin the API version so a behind-the-scenes Stripe dashboard
    # change doesn't alter response shapes under our feet.
    stripe.api_version = "2024-12-18.acacia"
    _configured = True


def get_stripe():
    """Return the configured stripe module, or raise 503 if unconfigured.

    Callers use it as:
        s = get_stripe()
        session = s.checkout.Session.create(...)

    The 503 is intentional: an unconfigured Stripe in a route that
    requires it means the operator hasn't set STRIPE_SECRET_KEY, which
    is a config problem, not a user error. Users shouldn't see "500";
    frontend can show a "billing unavailable — contact support" copy.
    """
    _configure_once()
    if not get_settings().STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is not configured on this environment.",
        )
    return stripe


def is_stripe_configured() -> bool:
    """Non-raising version for health checks / conditional UI."""
    return bool(get_settings().STRIPE_SECRET_KEY)
