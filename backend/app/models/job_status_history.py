"""
JobStatusHistory — append-only log of status transitions per job.

Why a separate table rather than columns on jobs:
    The dashboard Sankey chart needs the FLOW between stages, not just
    the current state. A single status column tells you "this job is
    currently at second_interview"; it cannot answer "how many of my
    applications got past first_interview before being rejected?". An
    append-only history row per transition makes the funnel computable
    without a denormalised counter cache.

Why denormalise user_id (already reachable via job.user_id):
    The funnel endpoint scans every history row owned by a single user,
    grouped by job, ordered by changed_at. Without a direct user_id we
    would either need to JOIN to jobs on every query or trust an index-
    only path through Postgres. Denormalisation keeps the index small
    (user_id, changed_at) and the query a single table scan.

Why allow `from_status = NULL`:
    The very first row for a job records the initial state (typically
    "saved") and has no predecessor. NULL is the honest representation
    of "this is where the journey starts". The funnel aggregation
    treats NULL → saved rows as the entry into the diagram.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPkMixin


class JobStatusHistory(Base, UUIDPkMixin):
    __tablename__ = "job_status_history"

    job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Denormalised — see module docstring. Cascade on user delete keeps
    # GDPR-style purges single-step.
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # NULL for the first row of a job's history (no prior state).
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)

    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Composite index for the dashboard funnel scan: filter by user,
    # order by time. Job-level scans (rare — only on PATCH for the
    # last-row lookup) hit the foreign-key index implicitly.
    __table_args__ = (
        Index("ix_job_status_history_user_changed", "user_id", "changed_at"),
        Index("ix_job_status_history_job_changed", "job_id", "changed_at"),
    )
