"""
Billing schemas — request/response shapes for the /billing routes.
"""

from datetime import datetime

from pydantic import BaseModel


class UsageItem(BaseModel):
    """One entry in the usage report for the frontend.

    `limit` is None for grandfathered users (unlimited); the UI shows
    the phrase "Unlimited" instead of a fraction.
    `remaining` is also None in that case.
    `resets_at` is the window_end — when the counter flips back to 0.
    """

    resource: str
    limit: int | None
    used: int
    remaining: int | None
    resets_at: datetime


class BillingStatusOut(BaseModel):
    """Full billing + usage snapshot driving the /billing page and
    dashboard pill.
    """

    plan: str
    subscription_status: str | None
    current_period_end: datetime | None
    cancel_at_period_end: bool

    # Per-user (scope='user') resource usage. Per-job resources aren't
    # aggregated here — they live on the job detail response so the
    # UI has per-job granularity where it matters.
    usage: list[UsageItem]


class CheckoutOut(BaseModel):
    """Response from POST /billing/checkout."""

    url: str


class PortalOut(BaseModel):
    """Response from POST /billing/portal."""

    url: str
