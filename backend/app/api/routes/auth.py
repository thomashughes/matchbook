"""
Authentication routes.

All eight flows from the handoff §6.1 are implemented here:
    register, verify-email, login, refresh, logout,
    forgot-password, reset-password, plus a /me helper.

Cross-cutting behaviours intentionally kept in this module:

1. Email enumeration resistance.
   /register and /forgot-password respond the same way whether the email
   exists or not. Otherwise a public attacker can use these endpoints as
   an oracle to check "is alice@example.com a Matchbook user?" which is
   a privacy leak.

2. Rate limiting.
   /login is limited per-IP under a distinct "login" bucket (10/min) so a
   brute-force password attempt is slowed without blocking legitimate
   /register traffic on the same IP. All other unauthenticated endpoints
   share the 20/min bucket.

3. Refresh token rotation.
   /refresh issues a new access token AND a new refresh cookie on every
   successful exchange. This limits the damage window of a stolen
   refresh token — once the legitimate user refreshes, the stolen one
   won't work past the rotation window. A full revocation list is out of
   scope for Phase 1 (Redis blacklist by jti is Phase 2 material).
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, get_current_user, rate_limit_unauth_ip
from app.core.config import get_settings
from app.core.database import get_db
from app.core.email import (
    consume_password_reset_token,
    consume_verification_token,
    issue_password_reset_token,
    issue_verification_token,
    password_reset_email_body,
    send_email,
    verification_email_body,
)
from app.core.rate_limit import (
    LIMIT_FORGOT_PASSWORD_EMAIL,
    LIMIT_FORGOT_PASSWORD_IP,
    LIMIT_LOGIN,
    LIMIT_REFRESH,
    LIMIT_RESEND_VERIFICATION,
    check_rate_limit,
)
from app.core.security import (
    ACCESS_TYPE,
    REFRESH_TYPE,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    deny_jti,
    hash_password,
    is_jti_denied,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordIn,
    LoginIn,
    MessageOut,
    RegisterIn,
    ResendVerificationIn,
    ResetPasswordIn,
    TokenOut,
    UserOut,
    VerifyEmailIn,
)

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])


# Cookie name for the refresh token. Distinct from "session" so we can
# evolve auth without colliding with other cookie-based features.
REFRESH_COOKIE = "mb_refresh"

# Cookie max-age in seconds derived from the JWT refresh TTL. We set
# both max_age and the JWT exp; the JWT is authoritative (the cookie
# TTL is just a client-side hint).
_REFRESH_MAX_AGE = int(timedelta(days=settings.JWT_REFRESH_TTL_DAYS).total_seconds())


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Apply the full set of hardening flags for the refresh cookie.

    httponly=True    — inaccessible to JavaScript, so XSS cannot steal it.
    secure=True      — browser refuses to send it over plain HTTP.
                       In local dev over HTTP, browsers ignore this on
                       localhost which is fine for development.
    samesite=strict  — the cookie is never sent on cross-site navigation
                       or XHR. A malicious site on another origin cannot
                       trigger a refresh using ambient credentials.
    path=/api/v1/auth — cookie is only sent on auth endpoints, never
                       leaked to unrelated API calls.

    Why no __Host- prefix: the prefix mandates Path=/ which would lift
    the path scoping above. Path-scoping the cookie to /api/v1/auth is
    the stronger constraint — the cookie can't even be observed by code
    outside the auth namespace. We deliberately trade __Host- for that.
    """
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=_REFRESH_MAX_AGE,
        httponly=True,
        secure=settings.ENVIRONMENT != "development",
        samesite="strict",
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


def _token_response(user_id, response: Response) -> JSONResponse:
    """Build the standard access+refresh response used by login & refresh."""
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    payload = TokenOut(
        access_token=access,
        expires_in_seconds=settings.JWT_ACCESS_TTL_MINUTES * 60,
    )
    resp = JSONResponse(content=payload.model_dump())
    _set_refresh_cookie(resp, refresh)
    return resp


# --- Register --------------------------------------------------------------


@router.post(
    "/register",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_unauth_ip)],
)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)) -> MessageOut:
    """Create an account and send a verification email.

    Enumeration note: we return the same 201 message whether the email
    is new or already registered. If the address is already in use, we
    silently skip creation but still behave as if we sent an email. This
    prevents attackers mapping out our user base via registration probes.
    """
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is None:
        user = User(email=body.email, password_hash=hash_password(body.password))
        db.add(user)
        try:
            await db.commit()
            await db.refresh(user)
        except IntegrityError:
            # Concurrent race — another request inserted the same email
            # between our SELECT and INSERT. Treat identically to the
            # "already exists" branch above.
            await db.rollback()
        else:
            # Issue the verification token and send the email *before* we
            # consider the registration a success. If SMTP fails, roll the
            # user row back so the address can be re-registered cleanly on
            # retry — otherwise a transient mail outage leaves orphan
            # accounts that can't verify and can't re-register.
            try:
                token = await issue_verification_token(str(user.id))
                subject, body_txt = verification_email_body(token)
                await send_email(user.email, subject, body_txt)
            except Exception:
                await db.delete(user)
                await db.commit()
                raise

    return MessageOut(message="If that email is new, we've sent a verification link.")


# --- Verify email ----------------------------------------------------------


@router.post(
    "/verify-email",
    response_model=MessageOut,
    dependencies=[Depends(rate_limit_unauth_ip)],
)
async def verify_email(body: VerifyEmailIn, db: AsyncSession = Depends(get_db)) -> MessageOut:
    user_id = await consume_verification_token(body.token)
    if not user_id:
        # Consume returns None for: never existed, already used, expired.
        # All three collapse to the same response for the same enumeration
        # reasons as /register.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    user.is_verified = True
    await db.commit()
    return MessageOut(message="Email verified. You can now log in.")


# --- Resend verification ---------------------------------------------------


@router.post(
    "/resend-verification",
    response_model=MessageOut,
    dependencies=[Depends(rate_limit_unauth_ip)],
)
async def resend_verification(
    body: ResendVerificationIn, db: AsyncSession = Depends(get_db)
) -> MessageOut:
    """Re-issue a verification email for an unverified account.

    Rate-limited two ways:
      1. Per-IP via the shared unauth bucket (20/min) — same as register.
      2. Per-email via LIMIT_RESEND_VERIFICATION (3/hour) — keyed by the
         submitted email so no inbox can be carpet-bombed regardless of
         the source IP.

    Enumeration-resistant: same MessageOut whether the address is unknown,
    already verified, or genuinely re-issued. We still consume the per-
    email limit on lookup so an attacker can't probe-then-resend without
    paying the cost.
    """
    # Check the per-email bucket BEFORE the DB lookup so a probe-flood
    # against unknown emails can't escape the limit.
    await check_rate_limit(body.email.lower(), LIMIT_RESEND_VERIFICATION)

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Already-verified accounts and unknown emails both fall through
    # silently — no oracle for the attacker.
    if user is not None and not user.is_verified:
        token = await issue_verification_token(str(user.id))
        subject, body_txt = verification_email_body(token)
        await send_email(user.email, subject, body_txt)

    return MessageOut(
        message="If that account exists and isn't verified, we've sent a new link."
    )


# --- Login -----------------------------------------------------------------


@router.post("/login")
async def login(
    body: LoginIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Exchange email+password for an access token and a refresh cookie.

    Rate-limited by IP under the dedicated login bucket (10/min). We
    deliberately don't rate-limit by email because that would let an
    attacker lock out a victim by submitting bad passwords for their
    account. Slowing the attacker's IP is the safer choice.
    """
    await check_rate_limit(client_ip(request), LIMIT_LOGIN)

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Always run verify_password, even on unknown email, to equalise the
    # response time between "user exists, wrong password" and "user
    # doesn't exist" — prevents timing-oracle user enumeration.
    dummy_hash = "$2b$12$" + "a" * 53  # well-formed bcrypt hash shape
    ok = verify_password(body.password, user.password_hash if user else dummy_hash)

    if not user or not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Unverified users cannot log in — we don't want unverified accounts
    # generating AI load. They can re-request a verification email
    # separately (not implemented in Phase 1; tracked for Phase 2).
    if not user.is_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Check your inbox for the verification link.",
        )

    return _token_response(user.id, Response())


# --- Refresh ---------------------------------------------------------------


@router.post("/refresh")
async def refresh(request: Request) -> JSONResponse:
    """Exchange the refresh cookie for a fresh access token (and rotate).

    Rate-limited at LIMIT_REFRESH (30/min/IP). The cookie itself is
    SameSite=Strict + httponly + path-scoped, so cross-site abuse is
    already blocked — the cap is defence-in-depth against a stolen-
    cookie replay flood, not against legitimate active clients.

    On rotation we revoke the OLD refresh jti so a leaked cookie can't
    be replayed once the legitimate browser has refreshed: classic
    refresh-token-rotation pattern.
    """
    await check_rate_limit(client_ip(request), LIMIT_REFRESH)

    cookie = request.cookies.get(REFRESH_COOKIE)
    if not cookie:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="No refresh cookie")

    try:
        decoded = decode_token(cookie, expected_type=REFRESH_TYPE)
    except TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    # Reject a refresh whose jti has already been used (logout, prior
    # rotation, manual revocation). Without this check, a stolen cookie
    # would remain valid until its 7-day exp.
    if await is_jti_denied(decoded.jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    # Burn the old jti before issuing the replacement: if anything goes
    # wrong after this point the user can re-login, but a leaked cookie
    # never gets a second use.
    await deny_jti(decoded.jti, decoded.exp)

    return _token_response(decoded.user_id, Response())


# --- Logout ----------------------------------------------------------------


@router.post("/logout", response_model=MessageOut)
async def logout(
    request: Request,
    response: Response,
    authorization: str | None = Header(default=None),
) -> MessageOut:
    """Clear the refresh cookie AND revoke both tokens immediately.

    Refresh side: pull the cookie, decode it, denylist the jti — even if
    the browser somehow keeps the cookie around or it's been copied
    elsewhere, it can't be used again.

    Access side: the frontend sends `Authorization: Bearer <access>` so
    we can denylist the live access jti too. Without this, a logged-out
    user's still-in-memory access token would remain accepted for up to
    15 minutes — uncomfortable on a shared machine.

    All decode failures are swallowed: logout must always succeed from
    the user's perspective, even with a malformed token. The cookie
    clear and the response shape don't change.
    """
    cookie = request.cookies.get(REFRESH_COOKIE)
    if cookie:
        try:
            decoded = decode_token(cookie, expected_type=REFRESH_TYPE)
            await deny_jti(decoded.jti, decoded.exp)
        except TokenError:
            pass

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            decoded = decode_token(token, expected_type=ACCESS_TYPE)
            await deny_jti(decoded.jti, decoded.exp)
        except TokenError:
            pass

    _clear_refresh_cookie(response)
    return MessageOut(message="Logged out")


# --- Forgot / reset password ----------------------------------------------


@router.post(
    "/forgot-password",
    response_model=MessageOut,
    dependencies=[Depends(rate_limit_unauth_ip)],
)
async def forgot_password(
    body: ForgotPasswordIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """Send a reset link if the email matches a user.

    Two-bucket rate limiting on top of the shared 20/min unauth bucket:
      - per IP, 10/hour (stops a single host carpet-bombing many users)
      - per email, 3/hour (stops rotating IPs targeting one inbox)
    Either bucket trips → 429 before the DB lookup, so an attacker can't
    use this route as an enumeration probe under the limit either.

    Same enumeration-resistant response pattern as /register. Token TTL
    is 1 hour (see email.RESET_TTL_SECONDS) — short because a leaked
    reset link gives an attacker full account takeover.
    """
    await check_rate_limit(client_ip(request), LIMIT_FORGOT_PASSWORD_IP)
    await check_rate_limit(body.email.lower(), LIMIT_FORGOT_PASSWORD_EMAIL)

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is not None:
        token = await issue_password_reset_token(str(user.id))
        subject, body_txt = password_reset_email_body(token)
        await send_email(user.email, subject, body_txt)
    return MessageOut(message="If that account exists, we've sent a reset link.")


@router.post(
    "/reset-password",
    response_model=MessageOut,
    dependencies=[Depends(rate_limit_unauth_ip)],
)
async def reset_password(
    body: ResetPasswordIn, db: AsyncSession = Depends(get_db)
) -> MessageOut:
    user_id = await consume_password_reset_token(body.token)
    if not user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    # Changing the password is a convenient moment to also mark the email
    # verified — the user just proved they control the inbox that received
    # the reset token, which is exactly what email verification tests.
    user.password_hash = hash_password(body.new_password)
    user.is_verified = True
    await db.commit()
    return MessageOut(message="Password updated. You can now log in.")


# --- Me --------------------------------------------------------------------


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    """Return the current user's public profile.

    Lets the frontend show/hide UI affordances without decoding the JWT
    itself — the source of truth stays on the server.
    """
    return UserOut(id=str(user.id), email=user.email, is_verified=user.is_verified)
