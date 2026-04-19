"""
CompanyResearchCache — cross-user cache of company research.

This table is intentionally NOT tenant-scoped — company facts don't vary
by user. Sharing the cache means the first user to research "Acme Corp"
pays the Claude/web-search cost and every subsequent user gets an instant
response. expires_at allows re-research periodically (news goes stale).
"""

from datetime import datetime
from uuid import UUID  # noqa: F401  (used by ORM infra via mapped_column typing)

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPkMixin


class CompanyResearchCache(Base, UUIDPkMixin):
    __tablename__ = "company_research_cache"

    # UNIQUE so lookups by company name are an index scan. Casing matters
    # at the app layer — we lowercase before storing/querying.
    company_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    research_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
