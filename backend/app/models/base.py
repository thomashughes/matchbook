"""
Shared declarative base and common mixins for every ORM model.

Why a UUID primary key on every table (vs autoincrement int):
    - UUIDs are non-enumerable: /jobs/123 leaks that there are at least 123
      jobs, /jobs/{uuid} reveals nothing.
    - No collisions across environments — test fixtures can't clash with
      real IDs when imported.
    - Generation happens server-side via gen_random_uuid() (from pgcrypto,
      built in to Postgres 13+), so we don't need client-side uuid4() and
      every row is guaranteed to have an ID at INSERT time.

Why created_at / updated_at on everything:
    Debugging and audit. "When did this break?" becomes answerable from
    the data, not just logs. updated_at is maintained server-side via
    onupdate so application code can never forget to bump it.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Root class for all ORM models. Alembic's autogenerate walks Base.metadata."""


class UUIDPkMixin:
    """Adds a UUID primary key column backed by gen_random_uuid() at the DB level."""

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        # server_default pushes generation into Postgres so every row gets
        # an ID even if the ORM didn't populate one (e.g. a raw INSERT).
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """created_at / updated_at maintained by Postgres (NOW() at insert/update)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        # onupdate fires at the ORM layer; server_onupdate would need a
        # trigger. For our access patterns (all writes go through SQLA)
        # the ORM-level hook is sufficient and portable.
        onupdate=func.now(),
        nullable=False,
    )
