"""
Transactional email via Plesk SMTP.

Why aiosmtplib / direct SMTP rather than a provider SDK (SendGrid / Postmark):
    The handoff specifies Plesk SMTP — Thomas already owns the domain and
    deliverability for tag-art.co.uk. Avoids adding a paid dependency to
    a portfolio project.

Why single-use tokens live in Redis and not the DB:
    - Automatic cleanup via TTL — no cron job to prune stale tokens.
    - Easy single-use semantics: DELETE on consume.
    - No migration needed if we change the token format.

Token shape:
    secrets.token_urlsafe(32) → ~43 char URL-safe base64. 256 bits of
    entropy — uniform random; guessing is computationally infeasible.
    We store a SHA-256 of the token as the Redis key (not the token
    itself) so that a Redis dump never reveals usable tokens. The raw
    token only ever exists in the email sent to the user.
"""

import asyncio
import hashlib
import secrets
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.rate_limit import get_redis

settings = get_settings()


# --- Token helpers ---------------------------------------------------------

# Namespaces ensure a password-reset token can't be accepted in place of an
# email-verification token even if keys collided (which they won't, but
# defense in depth).
_VERIFY_NS = "tok:verify"
_RESET_NS = "tok:reset"

# TTLs chosen to balance UX vs. attacker window.
VERIFY_TTL_SECONDS = 60 * 60 * 24       # 24h — users sometimes verify next day
RESET_TTL_SECONDS = 60 * 60             # 1h — security-sensitive, shorter


def _hash_token(raw: str) -> str:
    """Hex SHA-256 of the raw token — what we actually store in Redis."""
    return hashlib.sha256(raw.encode()).hexdigest()


async def _issue(namespace: str, user_id: str, ttl: int) -> str:
    """Generate a token, store a hashed copy keyed by hash → user_id."""
    raw = secrets.token_urlsafe(32)
    key = f"{namespace}:{_hash_token(raw)}"
    await get_redis().set(key, user_id, ex=ttl)
    return raw


async def _consume(namespace: str, raw: str) -> str | None:
    """Look up & atomically delete a token. Returns user_id or None.

    Uses GETDEL so the token cannot be used twice — even in a race between
    two concurrent verification requests, only one wins. If GETDEL is
    unavailable (Redis < 6.2) we'd fall back to GET+DEL in a MULTI/EXEC;
    Redis 7 (in our stack) supports GETDEL natively.
    """
    key = f"{namespace}:{_hash_token(raw)}"
    return await get_redis().getdel(key)


async def issue_verification_token(user_id: str) -> str:
    return await _issue(_VERIFY_NS, user_id, VERIFY_TTL_SECONDS)


async def consume_verification_token(raw: str) -> str | None:
    return await _consume(_VERIFY_NS, raw)


async def issue_password_reset_token(user_id: str) -> str:
    return await _issue(_RESET_NS, user_id, RESET_TTL_SECONDS)


async def consume_password_reset_token(raw: str) -> str | None:
    return await _consume(_RESET_NS, raw)


# --- Sending ---------------------------------------------------------------


def _send_sync(to: str, subject: str, body: str) -> None:
    """Blocking SMTP send. Runs in a thread via asyncio.to_thread."""
    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    # STARTTLS upgrades the plaintext socket to TLS before authentication so
    # credentials are never sent in clear. SMTP_VERIFY_TLS=false skips cert
    # validation — the right choice when reaching a local Plesk postfix
    # over the docker bridge, where traffic never leaves the host but the
    # server presents a self-signed cert.
    ctx = ssl.create_default_context()
    if not settings.SMTP_VERIFY_TLS:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as s:
        s.starttls(context=ctx)
        if settings.SMTP_USER:
            s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        s.send_message(msg)


async def send_email(to: str, subject: str, body: str) -> None:
    """Fire-and-forget async wrapper.

    If SMTP is unconfigured (local dev without creds) we log to stdout so
    developers can copy verification links without a real SMTP server. We
    detect "unconfigured" by empty SMTP_HOST — the template's default.
    """
    if not settings.SMTP_HOST:
        # Dev fallback. Loud enough to notice in container logs.
        print(f"[EMAIL:DEV] to={to} subject={subject!r}\n{body}\n", flush=True)
        return
    await asyncio.to_thread(_send_sync, to, subject, body)


def verification_email_body(token: str) -> tuple[str, str]:
    link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    subject = "Verify your Matchbook account"
    body = (
        f"Welcome to Matchbook.\n\n"
        f"Click the link below to verify your email address:\n\n{link}\n\n"
        f"This link expires in 24 hours. If you didn't sign up, ignore this email."
    )
    return subject, body


def password_reset_email_body(token: str) -> tuple[str, str]:
    link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    subject = "Reset your Matchbook password"
    body = (
        f"A password reset was requested for your Matchbook account.\n\n"
        f"Click the link below to set a new password:\n\n{link}\n\n"
        f"This link expires in 1 hour. If you didn't request this, ignore "
        f"this email — your password will remain unchanged."
    )
    return subject, body
