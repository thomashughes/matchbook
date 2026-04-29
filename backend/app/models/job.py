"""
Job model — each row is one job a user has saved/applied to.
"""

from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class Job(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "jobs"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        # Composite-capable index; most queries filter by user first.
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Structured salary range for comparisons + the raw string we pulled
    # from the description, kept so we can show the user exactly what the
    # listing said (ranges often include "OTE", "+ benefits" etc.).
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Full description stored so re-scoring after profile updates doesn't
    # need to re-fetch from the original source (which may have 404'd).
    description_raw: Mapped[str] = mapped_column(Text, nullable=False)

    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # One of: paste | url | file | extension.
    # VARCHAR(20) with an app-level enum, not a DB ENUM — easier to add
    # new source types later without an Alembic migration for the type.
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Application funnel state. Allowed values come from
    # schemas.jobs.JobStatusLiteral; the column is plain VARCHAR rather
    # than a DB ENUM so adding a future stage is one Pydantic edit, not
    # an Alembic migration. Width 30 fits all current values plus
    # comfortable headroom.
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="saved")

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Snapshot of users.profile_version at the moment this job was last
    # scored. When it differs from the user's current profile_version,
    # the UI shows a stale-score banner prompting a re-score. NULL means
    # the job has never been scored yet (no banner in that state).
    scored_against_profile_version: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
