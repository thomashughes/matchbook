"""
CvVersion — AI-generated CV drafts, with in-place user edits.

One row per AI generation. User edits in the inline rich editor update
content_markdown in place; they do NOT create new rows (that would fill
the version list with every keystroke). New rows only appear when the
user explicitly regenerates, at which point regenerate_reason captures
what they wanted different.

Why Markdown as the canonical format:
    TipTap round-trips Markdown cleanly, the PDF renderer accepts it
    directly via markdown-it, and users can download the source for
    external tools. Plain-text or HTML would each tie us to one output
    path — Markdown is the join point.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPkMixin


class CvVersion(Base, UUIDPkMixin):
    __tablename__ = "cv_versions"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Monotonic per user. A UNIQUE (user_id, version) DB constraint makes
    # concurrent generations serialise rather than both land at the same
    # number — the second one retries.
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)

    # 'professional' | 'bold'. VARCHAR (not DB enum) so adding tones
    # later needs no migration.
    tone: Mapped[str] = mapped_column(String(32), nullable=False)

    # { "questions": [...], "answers": {...}, "extra": "..." } — full
    # Phase-1 payload + what the user typed. Auditable so we can diff
    # across versions to explain why one is better than another.
    questions_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Populated on the 2nd+ generation within a cycle; null on version 1.
    # Fed straight into the Phase-2 user message so the regeneration is
    # actually informed by the user's dissatisfaction with v1.
    regenerate_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Snapshot of users.profile_version at generation time. Used by the
    # UI to mark this version as "generated against previous profile"
    # after a rebuild — same mechanism as jobs and cover_letters.
    profile_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
