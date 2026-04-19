"""
JobAIOutput — a generic table backing the non-letter AI actions on a job:
outreach messages, form-question responses, follow-ups, and interview
prep. Cover letters keep their own table because they have a richer,
more stable schema (tone + length) already in production use.

Why one table for the rest: the shape is identical — prompt-configured
input (kept in `params` JSONB) produces a text blob (`content`),
version-numbered per (job, kind). Collapsing them avoids four
near-duplicate tables, four migrations, four route files. The `kind`
column is the discriminator; all queries filter on it.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPkMixin


class JobAIOutput(Base, UUIDPkMixin):
    __tablename__ = "job_ai_outputs"

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

    # outreach | form_response | follow_up | interview_prep
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Kind-specific knobs (channel, recipient_role, question, etc.) — kept
    # as JSONB so new kinds don't need schema migrations. Rendered back to
    # the UI so the user can see how a given version was produced.
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Monotonic per (job_id, kind). App assigns max+1 on insert.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
