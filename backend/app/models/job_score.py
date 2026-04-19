"""
JobScore — Claude's scored evaluation of a user's profile against a job.
Separate table from jobs because:
    - A job can be re-scored over time (profile updates, prompt improvements).
      We could keep history by not deleting old rows.
    - It lets us skip the join when listing jobs without scores.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPkMixin


class JobScore(Base, UUIDPkMixin):
    __tablename__ = "job_scores"

    job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalised user_id so tenant-scoped queries don't need a join
    # through jobs — every list/where clause filters on user_id first.
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    total_score: Mapped[int] = mapped_column(Integer, nullable=False)
    skills_score: Mapped[int] = mapped_column(Integer, nullable=False)
    experience_score: Mapped[int] = mapped_column(Integer, nullable=False)
    salary_score: Mapped[int] = mapped_column(Integer, nullable=False)
    location_score: Mapped[int] = mapped_column(Integer, nullable=False)
    culture_score: Mapped[int] = mapped_column(Integer, nullable=False)
    trajectory_score: Mapped[int] = mapped_column(Integer, nullable=False)

    # JSONB arrays of short strings. Shape is validated with Pydantic
    # against the Claude response before we ever write here, so the DB
    # can trust the structure.
    strengths: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    weaknesses: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    red_flags: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
