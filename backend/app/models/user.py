"""
The User model — root of every tenant's data graph.

Tenancy note:
    This is a multi-tenant app with per-user isolation. Every data table
    that follows has a user_id FK → users(id) with CASCADE DELETE. That
    cascade matters — deleting a user must remove every trace (GDPR Art.
    17 right-to-erasure). We enforce the WHERE user_id = :current_user_id
    filter at the ORM/dependency layer too, belt-and-braces.
"""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class User(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "users"

    # Email is the login identifier. UNIQUE at the DB level so a race
    # between two concurrent registrations can't create duplicates — one
    # of them gets an IntegrityError and the route converts it to 409.
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # bcrypt hash, NOT the plaintext. Never store plaintext anywhere, ever.
    # 255 chars is plenty; a bcrypt hash is 60 characters.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Users start unverified. Most protected features (job scoring, CV
    # upload) should also require is_verified — enforced at the dep layer,
    # not here, so we can carve out exceptions if needed.
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Fernet-encrypted Google OAuth credentials (refresh token + access
    # token). Stored as TEXT because Fernet output is base64. Encryption
    # at rest means a DB dump alone can't be used to impersonate users'
    # Google accounts — the FERNET_KEY is required and lives only in env.
    google_calendar_credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
