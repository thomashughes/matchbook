"""
Pydantic schemas for auth endpoints.

Why a separate schema layer (vs returning ORM models directly):
    - Keeps our DB schema decoupled from our API contract. Adding an
      internal column (e.g. a spam-score) won't accidentally leak it to
      the frontend.
    - Validation of inbound data happens here in one declarative spot.
    - OpenAPI docs become accurate because FastAPI introspects these.
"""

from pydantic import BaseModel, EmailStr, Field, field_validator


# bcrypt's input is silently truncated at 72 bytes. Two distinct passwords
# whose first 72 UTF-8 bytes are identical therefore hash to the same value
# — a subtle collision risk that's easy to overlook because it only bites
# users with very long passwords. Refuse anything past the limit at the
# validation layer so the truncation never happens.
_BCRYPT_MAX_BYTES = 72


def _password_within_bcrypt_limit(v: str) -> str:
    if len(v.encode("utf-8")) > _BCRYPT_MAX_BYTES:
        raise ValueError(
            f"Password is too long ({_BCRYPT_MAX_BYTES} bytes max). "
            "Each emoji or non-ASCII letter counts as several bytes."
        )
    return v


# --- Input schemas ---------------------------------------------------------


class RegisterIn(BaseModel):
    # EmailStr enforces syntactic email validity. Deliverability is checked
    # via the verification email, not here.
    email: EmailStr
    # 8 char min is NIST SP 800-63B guidance floor. Char max is generous so
    # we don't surprise users typing a long passphrase; the byte-level cap
    # in _password_within_bcrypt_limit is the load-bearing constraint.
    password: str = Field(min_length=8, max_length=128)

    _validate_password = field_validator("password")(_password_within_bcrypt_limit)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    # No byte-level validator on /login: rejecting an over-72-byte input
    # at this layer would leak that bcrypt is the backend (an attacker
    # submitting a 200-char string would get a different error than for
    # a wrong password). Instead the verify path simply fails to match.


class VerifyEmailIn(BaseModel):
    token: str = Field(min_length=16, max_length=256)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResendVerificationIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)

    _validate_new_password = field_validator("new_password")(_password_within_bcrypt_limit)


# --- Output schemas --------------------------------------------------------


class TokenOut(BaseModel):
    """Access-token response. Refresh token is set as a cookie, not in
    this body, so JavaScript on the frontend cannot read it."""

    access_token: str
    token_type: str = "Bearer"
    expires_in_seconds: int


class MessageOut(BaseModel):
    """Generic message payload. We reuse this across endpoints so the
    frontend has a consistent shape for 'success but no data' responses."""

    message: str


class UserOut(BaseModel):
    """Public view of a user. Notably absent: password_hash, token blobs."""

    id: str
    email: EmailStr
    is_verified: bool
