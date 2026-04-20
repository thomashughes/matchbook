"""
UsageCounter — monthly usage tracking per (user, resource, optional scope).

Why a dedicated table rather than Redis:
    Redis is used for burst rate limiting (LIMIT_AI at 60/min) where the
    window is short and data loss on restart is tolerable. Entitlements
    are a billing-adjacent concern: a user who used 4/5 jobs this month
    must still see "4/5" after a Redis eviction or a deploy. Postgres is
    the source of truth.

Why per-resource rows instead of a JSONB column on users:
    - Atomic UPSERT + RETURNING is straightforward with a unique index
      on (user_id, resource, scope_key, window_start); concurrent
      consumes never corrupt the count.
    - Historical windows remain queryable ("you used 42 drafts last
      month") for free — just don't DELETE old rows. A later cron can
      prune if the table grows.
    - Schema stays readable to anyone doing DB archaeology; JSONB on a
      hot table doesn't.

scope_key is NULL for per-user resources (jobs_created,
company_research, ai_job_search). For per-job resources (draft_*,
cover_letter) it holds the job_id so a user's 3/mo draft_outreach cap
applies separately to each job.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPkMixin


class UsageCounter(Base, UUIDPkMixin):
    __tablename__ = "usage_counters"
    __table_args__ = (
        # One row per (user, resource, scope_key, window). Postgres treats
        # NULLs as distinct in a UNIQUE index by default — which is the
        # behaviour we want: a per-user resource (scope_key=NULL) gets one
        # row per window; a per-job resource gets one row per (job, window).
        UniqueConstraint(
            "user_id",
            "resource",
            "scope_key",
            "window_start",
            name="uq_usage_counter_user_resource_scope_window",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Matches a key in entitlements.RESOURCES. VARCHAR (not enum) so new
    # resources can be added without a migration for the type.
    resource: Mapped[str] = mapped_column(String(32), nullable=False)

    # For per-job resources this is the job_id. For per-user resources
    # it's NULL. Not a FK — scope_key's meaning depends on the resource,
    # and enforcing FK to jobs(id) would require a discriminator column
    # we don't have reason to add yet.
    scope_key: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )

    # Inclusive start / exclusive end of the billing window this row
    # belongs to. Anchored to user.created_at day-of-month (see
    # entitlements.current_window for the math, including the Feb-29
    # edge case).
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Monotonic within a window. Only incremented by consume(); refund()
    # decrements on AI-call failure. UPSERT uses
    # `INSERT ... ON CONFLICT ... DO UPDATE SET count = usage_counters.count + 1
    #  RETURNING count` so concurrent consumes never race.
    count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
