"""
CoverLetter — generated letters tied to a job. Multiple versions per job
are allowed so users can compare tones/lengths before sending.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPkMixin


class CoverLetter(Base, UUIDPkMixin):
    __tablename__ = "cover_letters"

    job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    # formal | conversational
    tone: Mapped[str] = mapped_column(String(20), nullable=False)
    # short | standard | detailed
    length: Mapped[str] = mapped_column(String(20), nullable=False)

    # Monotonic counter per job — app code assigns max(version)+1 on insert.
    # A composite UNIQUE (job_id, version) could prevent duplicates; left
    # off to avoid locking pain on concurrent generation.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Snapshot of users.profile_version at generation time. Drives the
    # "generated against a previous profile" stale banner after a rebuild.
    profile_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
