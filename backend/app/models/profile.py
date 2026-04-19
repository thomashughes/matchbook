"""
Profile and ProfileAnswer models.

Design notes:
    The profile is largely free-form data shaped by Claude — skills lists,
    salary expectations, working-style notes. Rather than normalise each
    of these into its own table (which would be over-engineered for
    mostly-read, rarely-queried data) we store them as JSONB columns.

    JSONB gives us GIN-indexable JSON in Postgres — good enough for
    filtering like "users with python in hard skills" later, without
    forcing a rigid schema up front while the product is still evolving.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class Profile(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "profiles"

    # 1:1 with users. We don't UNIQUE the FK at the model level because
    # Phase 2 may allow multi-CV (one profile per CV). The migration sets
    # a unique index we can drop later if that's introduced.
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Raw text extracted from the uploaded CV. Kept for re-analysis when
    # prompts improve — we don't want to ask users to re-upload their CV
    # every time we refine the parsing prompt.
    cv_raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Absolute path on the uploads volume. Files live outside the web
    # root (see §4.3 file upload security).
    cv_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # The full Claude-generated structured view of the candidate. Split
    # hot fields out into dedicated columns below for fast filtering.
    structured_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    skills_hard: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    skills_soft: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    seniority_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_ideal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_preferences: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    remote_preference: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notice_period: Mapped[str | None] = mapped_column(String(50), nullable=True)
    career_goals: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProfileAnswer(Base, UUIDPkMixin):
    """One Q&A pair from the conversational onboarding.

    Separate table (not a JSONB array on profiles) so individual answers
    can be re-asked / edited without rewriting the whole profile blob.
    No updated_at — answers are immutable; editing creates a new row.
    """

    __tablename__ = "profile_answers"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
