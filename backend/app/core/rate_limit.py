"""
Redis-backed rate limiting using a fixed-window counter.

Why Redis, not in-memory:
    In-memory counters die with the process, don't share across workers,
    and reset on deploy. Redis survives restarts, is shared across every
    uvicorn worker, and is already in the stack for other reasons.

Why fixed window and not token bucket (yet):
    Fixed window is trivially correct: INCR + EXPIRE. Token buckets need
    either Lua scripts or careful race handling. For auth endpoints the
    extra precision isn't worth the complexity — a hard 20/min at the
    window boundary is fine. We can upgrade to a sliding window / bucket
    in Phase 2 if the AI endpoints warrant it.

Keying strategy:
    Unauthenticated endpoints: key = "rl:ip:{ip}:{bucket_name}"
    Authenticated endpoints:   key = "rl:user:{user_id}:{bucket_name}"
    Keying by user (not IP) on authenticated endpoints prevents attackers
    sharing a NAT (corporate/campus networks) from being blocked by a
    single bad actor — and prevents a single user from bypassing limits
    by rotating IPs on a VPN.
"""

from dataclasses import dataclass

import redis.asyncio as aioredis
from fastapi import HTTPException, status

from app.core.config import get_settings

settings = get_settings()

# Module-level async client. redis-py handles connection pooling internally
# and is safe to share across coroutines. One client per process.
_redis: aioredis.Redis = aioredis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
)


def get_redis() -> aioredis.Redis:
    """Accessor so tests can monkeypatch the client."""
    return _redis


@dataclass(frozen=True)
class RateLimit:
    """One rate-limit configuration.

    name:    Namespace in the Redis key, so different endpoints don't share
             a single counter (login attempts shouldn't block registrations).
    limit:   Max requests allowed in the window.
    window:  Window length in seconds.
    """

    name: str
    limit: int
    window: int


# Preset limits pulled from the handoff §4.2. Centralised here so the
# numbers are auditable in one place rather than scattered through routes.
LIMIT_AUTH_UNAUTH = RateLimit("auth_unauth", limit=20, window=60)
LIMIT_LOGIN = RateLimit("login", limit=10, window=60)
# Refresh is keyed by IP (no authenticated user yet — they're presenting
# the cookie precisely to prove identity). 30/min comfortably covers a
# legitimate active session refreshing every ~10 min, while caging a
# stolen-cookie replay flood.
LIMIT_REFRESH = RateLimit("refresh", limit=30, window=60)
LIMIT_AI = RateLimit("ai", limit=60, window=60)
LIMIT_CV_UPLOAD = RateLimit("cv_upload", limit=5, window=60 * 60 * 24)
# Resend-verification is keyed BY EMAIL (not IP) so a single inbox can't
# be carpet-bombed even from rotating addresses. 3/hour is more than
# enough for a real user retrying — anything beyond that is abuse.
LIMIT_RESEND_VERIFICATION = RateLimit("resend_verify", limit=3, window=60 * 60)


async def check_rate_limit(identifier: str, rule: RateLimit) -> dict[str, str]:
    """Atomically increment the counter for this identifier+rule.

    Returns a dict of RateLimit-* headers to attach to the response so
    clients can back off gracefully. Raises 429 on breach.

    Implementation note — why INCR + EXPIRE (not SET NX EX):
        The first INCR on a fresh key returns 1; we then set a TTL only on
        that first call. This keeps the window anchored to the FIRST
        request rather than resetting every time. Subsequent INCRs just
        tick the counter; when TTL expires, the key vanishes and the next
        request starts a new window.

    Race note: between INCR and EXPIRE a crash would leave a counter
    without a TTL — it would never reset. To make this truly atomic
    we'd use a Lua script or SET with PX NX then INCR. The consequence
    here is bounded (one user stuck at their limit until a manual DEL),
    so we accept the simpler code for auth rate limiting.
    """
    key = f"rl:{rule.name}:{identifier}"
    r = get_redis()

    current = await r.incr(key)
    if current == 1:
        # First hit in this window — anchor the TTL.
        await r.expire(key, rule.window)

    ttl = await r.ttl(key)
    remaining = max(rule.limit - current, 0)

    headers = {
        "X-RateLimit-Limit": str(rule.limit),
        "X-RateLimit-Remaining": str(remaining),
        # Seconds until reset. Some clients prefer an absolute timestamp;
        # relative is simpler and avoids clock-skew debates.
        "X-RateLimit-Reset": str(max(ttl, 0)),
    }

    if current > rule.limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
            headers={**headers, "Retry-After": str(max(ttl, 1))},
        )

    return headers
