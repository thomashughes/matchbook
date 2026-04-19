"""
Centralised application configuration.

Why pydantic-settings rather than reading os.environ ad-hoc:
    - Config is validated once at startup — a missing ANTHROPIC_API_KEY
      crashes the process immediately instead of failing on the first
      Claude call hours later.
    - Types are enforced (JWT_ACCESS_TTL_MINUTES is an int, not "15").
    - All config is in one place so a reader can see every knob the app has
      without grepping for `os.getenv`.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables.

    Fields without a default are REQUIRED — the app refuses to start without
    them. This is deliberate: production misconfigurations should be loud.
    """

    model_config = SettingsConfigDict(
        # .env is read for local development. In production (Docker) the
        # variables are set directly on the container, and .env is absent.
        env_file=".env",
        env_file_encoding="utf-8",
        # Extra keys in .env are ignored rather than raising — useful
        # because docker-compose's env block may contain app-unrelated vars.
        extra="ignore",
    )

    # --- Environment -------------------------------------------------------
    ENVIRONMENT: Literal["development", "production", "test"] = "development"

    # --- Database ----------------------------------------------------------
    # Async URL used by the FastAPI app at runtime.
    DATABASE_URL: str
    # Sync URL used only by Alembic (migrations are synchronous by design).
    DATABASE_URL_SYNC: str

    # --- Redis -------------------------------------------------------------
    REDIS_URL: str

    # --- JWT (RS256) -------------------------------------------------------
    # Paths to PEM files mounted into the container. We read files rather
    # than pasting multi-line PEMs into env vars — newline handling in env
    # vars is error-prone and has burned every team that tried.
    JWT_PRIVATE_KEY_PATH: str
    JWT_PUBLIC_KEY_PATH: str
    JWT_ACCESS_TTL_MINUTES: int = 15
    JWT_REFRESH_TTL_DAYS: int = 7
    JWT_ALGORITHM: str = "RS256"

    # --- Fernet (symmetric encryption for OAuth tokens at rest) -----------
    FERNET_KEY: str = ""

    # --- Anthropic ---------------------------------------------------------
    # Optional in Phase 1 (auth-only). Enforced in Phase 2 when Claude is used.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5"

    # --- Google OAuth ------------------------------------------------------
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # --- SMTP --------------------------------------------------------------
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "Matchbook <noreply@localhost>"
    # Plesk postfix presents a self-signed cert on localhost; verifying would
    # reject every connection. When STARTTLS goes over the docker bridge to
    # the host the traffic never leaves the machine, so TLS here is for
    # credential protection, not authenticity. Set false in prod (VPS with
    # local postfix); leave true if pointing at an external SMTP provider.
    SMTP_VERIFY_TLS: bool = True

    # --- App URLs / CORS ---------------------------------------------------
    FRONTEND_URL: str = "http://localhost:3085"
    # Stored as a comma-separated string in env and parsed to a list.
    # Pydantic handles JSON-array env values too, but CSV is easier to
    # write in a .env by hand.
    CORS_ORIGINS: str = "http://localhost:3085"

    # --- Security knobs ----------------------------------------------------
    # bcrypt cost factor. 12 is the spec minimum (~250ms/hash on modern
    # hardware — slow enough to resist offline brute force, fast enough to
    # not DoS our own login endpoint).
    BCRYPT_ROUNDS: int = 12

    # --- Derived helpers ---------------------------------------------------
    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS_ORIGINS string into a list."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def jwt_private_key(self) -> str:
        """Read the private PEM from disk on first access.

        Cached by @lru_cache on get_settings(), so the file is read once per
        process. We don't hold it as a field to avoid it accidentally
        appearing in a Settings repr / debug log.
        """
        return Path(self.JWT_PRIVATE_KEY_PATH).read_text()

    @property
    def jwt_public_key(self) -> str:
        return Path(self.JWT_PUBLIC_KEY_PATH).read_text()

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _non_empty_cors(cls, v: str) -> str:
        # Empty CORS in production would let any origin through after we
        # default it — fail loudly instead.
        if not v.strip():
            raise ValueError("CORS_ORIGINS must list at least one origin")
        return v


@lru_cache
def get_settings() -> Settings:
    """Singleton accessor.

    @lru_cache makes this effectively a module-level singleton while
    remaining test-friendly — tests can call `get_settings.cache_clear()`
    then monkeypatch env vars to reload.
    """
    return Settings()  # type: ignore[call-arg]
