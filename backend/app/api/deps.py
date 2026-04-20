"""
Shared FastAPI dependencies.

get_current_user is the single choke point for authentication. Every
protected route declares it via Depends, and every database query must
scope to the returned user's id. Centralising auth here (rather than
copying logic into each route) means an auth bug has exactly one place
to live.
"""

from typing import Callable
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Path, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.entitlements import consume
from app.core.rate_limit import LIMIT_AUTH_UNAUTH, check_rate_limit
from app.core.security import ACCESS_TYPE, TokenError, decode_token
from app.models.user import User


def client_ip(request: Request) -> str:
    """Extract the originating client IP.

    Behind Apache reverse proxy we trust X-Forwarded-For's *first* entry —
    subsequent entries can be spoofed by the client. Apache's vhost config
    is responsible for stripping any X-Forwarded-For the client sent and
    replacing it with its own; if that config is missing, this function
    is the weak link for IP-based rate limiting. Documented risk.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def rate_limit_unauth_ip(request: Request) -> None:
    """Apply the default 20/min per-IP cap on unauthenticated endpoints."""
    await check_rate_limit(client_ip(request), LIMIT_AUTH_UNAUTH)


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve an Authorization: Bearer <jwt> header to a User row.

    Why header-based and not cookie-based for the access token:
        Access tokens live in JS memory on the frontend and are attached
        to each request in an Authorization header. This means CSRF is
        not a concern for protected endpoints (no ambient cookie to ride
        on). The refresh token lives in a cookie precisely because we
        WANT it sent automatically — but only to /auth/refresh, which
        uses SameSite=Strict as its CSRF defence.

    Every failure returns a generic 401 with no detail: we don't
    distinguish "no header" from "expired" from "bad signature" because
    that differentiation is useful only to attackers.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = authorization.split(" ", 1)[1].strip()
    try:
        user_id: UUID = decode_token(token, expected_type=ACCESS_TYPE)
    except TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        # Token is valid but user was deleted. Treat as logged-out.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


async def rate_limit_ai(user: User = Depends(get_current_user)) -> None:
    """Per-user cap on AI endpoints (10/min). Keyed by user_id, not IP:
    spec §4.2 — prevents shared-IP users blocking each other, and
    prevents a single attacker rotating IPs to bypass the cap."""
    from app.core.rate_limit import LIMIT_AI, check_rate_limit
    await check_rate_limit(str(user.id), LIMIT_AI)


async def rate_limit_cv_upload(user: User = Depends(get_current_user)) -> None:
    """5 CV uploads per day per user. CV parse is the most expensive
    Claude call we make, and the only storage operation — a tight daily
    cap prevents both cost runaway and disk abuse."""
    from app.core.rate_limit import LIMIT_CV_UPLOAD, check_rate_limit
    await check_rate_limit(str(user.id), LIMIT_CV_UPLOAD)


def entitlement(resource: str, scope: str = "user") -> Callable:
    """Build a FastAPI dependency that consumes one unit of `resource`.

    Usage:
        @router.post(..., dependencies=[Depends(entitlement("jobs_created"))])
        @router.post(..., dependencies=[Depends(entitlement("draft_outreach", "job"))])

    Why a factory: we need per-route parameterisation (resource name,
    scope) but FastAPI deps are functions. Closing over the args gives
    each route its own dep identity so FastAPI doesn't cache across
    routes unexpectedly.

    Scope semantics:
        - 'user': scope_key is NULL, counter is per-user-per-month.
        - 'job':  scope_key is the {job_id} path parameter. If the path
          doesn't contain {job_id} FastAPI's Path() resolver raises
          422, so a misconfiguration fails at the first request.

    Raises 402 QuotaExceeded if the user is over their plan limit for
    this resource. The route NEVER sees a successful entitlement without
    the counter having been incremented — consume() commits eagerly.

    Refund-on-failure: the dep only CONSUMES. Refunding on AI-call
    failure is the route's responsibility (see the routes themselves
    for the try/except/refund pattern). Splitting it this way keeps
    the dep composable — if a future route wants to consume without
    ever refunding (e.g. an internal ops action), it doesn't inherit
    refund logic it doesn't need.
    """
    if scope not in ("user", "job"):
        raise ValueError(f"entitlement scope must be 'user' or 'job', got {scope!r}")

    if scope == "user":
        async def _dep_user(
            user: User = Depends(get_verified_user),
            db: AsyncSession = Depends(get_db),
        ) -> None:
            await consume(db, user, resource, scope_key=None)
        return _dep_user

    # scope == "job"
    async def _dep_job(
        job_id: UUID = Path(...),
        user: User = Depends(get_verified_user),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        await consume(db, user, resource, scope_key=job_id)
    return _dep_job


async def get_verified_user(user: User = Depends(get_current_user)) -> User:
    """Require the user's email to be verified.

    Used on endpoints that consume paid resources (Claude calls) or store
    significant data (CV upload) — we don't want unverified throwaway
    addresses burning API credits.
    """
    if not user.is_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )
    return user
