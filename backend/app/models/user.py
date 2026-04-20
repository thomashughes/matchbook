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

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


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

    # Billing / entitlement plan. One of: 'free' | 'paid' | 'paid_grandfathered'.
    # 'paid_grandfathered' is an admin-level override used for the developer
    # account — unlimited on every resource regardless of Stripe state.
    # Stored as VARCHAR (not a DB ENUM) so adding future tiers doesn't need
    # an Alembic type migration.
    plan: Mapped[str] = mapped_column(
        String(20), nullable=False, default="free", server_default="free"
    )

    # Stripe customer record for this user. Populated on first Checkout
    # session creation. Kept after subscription cancellation so a returning
    # user reuses their Stripe customer (consolidates invoices + cards).
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )

    # Stripe subscription the user currently has (if any). Cleared when
    # the subscription is deleted. NULL for free users and for paid users
    # whose subscription has been canceled + reached period end.
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )

    # Mirror of Stripe's subscription.status string — 'active', 'past_due',
    # 'canceled', 'incomplete_expired', etc. Used to drive UI copy. The
    # plan column is the authoritative entitlement signal; this is purely
    # informational.
    subscription_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # When the current billing period ends. Drives the "cancelling on
    # <date>" UX and the grace-period cutoff: if cancel_at_period_end is
    # true, the plan flips to 'free' when this moment passes (via the
    # subscription.deleted webhook, not a cron — we let Stripe fire it).
    subscription_current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Set when the user requests cancellation via the Customer Portal.
    # Until the period ends they keep paid entitlements; after, Stripe
    # fires subscription.deleted and we flip plan to 'free'. Surfaced to
    # the frontend so it can display "cancelling on <date>".
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
