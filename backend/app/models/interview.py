"""
InterviewEvent — scheduled interview tied to a job.

google_event_id is the ID Google Calendar returned when we created the
event via OAuth. We store it so that edits/deletions on our side can
propagate to Google (PATCH/DELETE against the same event). If the user
never connected Calendar, the column is NULL and we only use it locally.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPkMixin


class InterviewEvent(Base, UUIDPkMixin):
    __tablename__ = "interview_events"

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

    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    # phone | video | in-person
    interview_type: Mapped[str] = mapped_column(String(30), nullable=False)
    interviewer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Physical address for in-person, URL for video.
    location_or_link: Mapped[str | None] = mapped_column(String(500), nullable=True)

    google_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
