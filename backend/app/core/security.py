"""
Authentication primitives: password hashing, JWT signing/verification,
and single-use token generation for email verification & password reset.

Security decisions made here (each is a deliverable-level explanation):

1. bcrypt for passwords, not SHA/PBKDF2/scrypt.
   - bcrypt has been battle-tested since 1999, has a tunable cost factor,
     and is the default in passlib. Cost 12 takes ~250ms per hash on
     modern hardware: slow enough to make offline cracking expensive,
     fast enough that a legitimate login is imperceptible.
   - Argon2 would be technically stronger, but passlib's bcrypt pathway
     is more mature and the difference is not meaningful for our threat
     model (leaked DB + offline attacker).

2. RS256 JWTs, not HS256.
   - HS256 uses a shared secret — anyone who can verify tokens can also
     forge them. RS256 splits this: the backend holds the private key
     and signs; anything else (future services, debuggers) can verify
     with just the public key. For a portfolio piece this also makes
     the security story crisper.

3. Access tokens are short-lived (15 min) and kept in memory on the
   frontend; refresh tokens are long-lived (7 days) in an httpOnly,
   Secure, SameSite=Strict cookie.
   - If an XSS bug leaks an access token, it expires in 15 minutes.
   - The refresh token is unreachable from JS (httpOnly), only sent over
     HTTPS (Secure), and never sent on cross-site requests (SameSite=
     Strict) — so it can't be silently used by a malicious third-party
     page even if the user is logged in on another tab.

4. Tokens for email verification / password reset are random 256-bit
   values (secrets.token_urlsafe) stored hashed in Redis with a TTL.
   They are NOT JWTs: there's no need for a signed payload, and single-
   use semantics are easier with Redis DEL than with JWT blacklists.
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

# passlib CryptContext abstracts over hash schemes and handles upgrades
# automatically — if we ever bump BCRYPT_ROUNDS or add argon2, passlib
# can transparently rehash on next login via needs_update().
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.BCRYPT_ROUNDS,
)


def hash_password(plain: str) -> str:
    """Hash a plaintext password for storage.

    Never log or return plain. This function is the only place plaintext
    passwords should ever touch — treat the argument as radioactive.
    """
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time check. passlib handles the timing-safe comparison."""
    return pwd_context.verify(plain, hashed)


# --- JWT --------------------------------------------------------------------

# Two separate token types so we can't accidentally accept a refresh token
# where an access token is expected (or vice versa). The claim name is
# "token_type" and is validated on every decode.
ACCESS_TYPE = "access"
REFRESH_TYPE = "refresh"


def _create_token(subject: UUID, token_type: str, ttl: timedelta) -> str:
    """Internal: build and sign a JWT with standard claims.

    Claims used:
        sub  — the user's UUID. This is what get_current_user reads.
        exp  — expiry (UTC). PyJWT enforces this on decode.
        iat  — issued-at. Useful for debugging and future revocation.
        jti  — unique token id. Phase-2 revocation list lookup key.
        token_type — our own claim; see note above.
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": now + ttl,
        "jti": secrets.token_urlsafe(16),
        "token_type": token_type,
    }
    return jwt.encode(payload, settings.jwt_private_key, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: UUID) -> str:
    return _create_token(
        user_id,
        ACCESS_TYPE,
        timedelta(minutes=settings.JWT_ACCESS_TTL_MINUTES),
    )


def create_refresh_token(user_id: UUID) -> str:
    return _create_token(
        user_id,
        REFRESH_TYPE,
        timedelta(days=settings.JWT_REFRESH_TTL_DAYS),
    )


class TokenError(Exception):
    """Raised when a token is malformed, expired, or of the wrong type.

    The API layer catches this and converts it to a 401. We never expose
    the internal reason to the client — all JWT failures look identical
    from the outside to prevent oracle-style probing.
    """


@dataclass(frozen=True)
class DecodedToken:
    """Outcome of a successful decode. Carries everything callers need
    to act on the token without re-parsing the JWT — `jti` for denylist
    checks/writes, `exp` for computing the remaining TTL when adding to
    the denylist (so revoked entries don't outlive the token itself)."""

    user_id: UUID
    jti: str
    exp: int  # Unix timestamp (seconds since epoch)


def decode_token(token: str, expected_type: str) -> DecodedToken:
    """Verify signature, expiry, and token_type. Return the decoded claims.

    Any failure path raises TokenError with no detail — routes translate
    that into a generic 401. This is deliberate; a detailed "token
    expired" vs "signature invalid" response helps attackers.

    Note: this function is signature-only; it does NOT check the Redis
    denylist. Revocation is checked in `is_jti_denied()` so that the
    pure-crypto path stays synchronous and call sites can opt in to the
    async Redis round-trip only when they need it.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.PyJWTError as e:
        raise TokenError("invalid token") from e

    if payload.get("token_type") != expected_type:
        # A refresh token submitted where an access token is expected
        # would otherwise bypass the shorter access TTL.
        raise TokenError("wrong token type")

    sub = payload.get("sub")
    if not sub:
        raise TokenError("missing subject")

    jti = payload.get("jti")
    if not jti or not isinstance(jti, str):
        # Tokens issued before the jti rollout will lack this claim. We
        # reject them outright rather than silently allowing an un-
        # revokable session — the worst case is one forced re-login on
        # deploy day, which is acceptable.
        raise TokenError("missing jti")

    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise TokenError("missing exp")

    try:
        user_id = UUID(sub)
    except ValueError as e:
        raise TokenError("malformed subject") from e

    return DecodedToken(user_id=user_id, jti=jti, exp=exp)


# --- Revocation denylist ---------------------------------------------------
#
# A logged-out or compromised token's jti is written to Redis with a TTL
# equal to its remaining lifetime. Decode paths consult this set before
# treating the token as valid. Once the JWT's own exp passes, the Redis
# key auto-expires too, so the denylist self-prunes.

_DENY_PREFIX = "jwt:denylist:"


async def is_jti_denied(jti: str) -> bool:
    """True if this token id is on the revocation list."""
    # Imported lazily to avoid a circular import: rate_limit imports
    # nothing from security, but security is imported very early in the
    # config chain — keeping the redis client lookup deferred sidesteps
    # any initialisation-order surprises.
    from app.core.rate_limit import get_redis

    return bool(await get_redis().exists(_DENY_PREFIX + jti))


async def deny_jti(jti: str, exp_ts: int) -> None:
    """Add jti to the denylist, with a TTL pinned to the token's own exp.

    No-op if the token is already past expiry — there's nothing left to
    revoke and we'd just be writing a key that immediately expires.
    """
    from app.core.rate_limit import get_redis

    now = int(datetime.now(timezone.utc).timestamp())
    ttl = exp_ts - now
    if ttl <= 0:
        return
    await get_redis().setex(_DENY_PREFIX + jti, ttl, "1")
