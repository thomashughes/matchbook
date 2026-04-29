"""
Pydantic schemas for auth endpoints.

Why a separate schema layer (vs returning ORM models directly):
    - Keeps our DB schema decoupled from our API contract. Adding an
      internal column (e.g. a spam-score) won't accidentally leak it to
      the frontend.
    - Validation of inbound data happens here in one declarative spot.
    - OpenAPI docs become accurate because FastAPI introspects these.
"""

from pydantic import BaseModel, EmailStr, Field


# --- Input schemas ---------------------------------------------------------


class RegisterIn(BaseModel):
    # EmailStr enforces syntactic email validity. Deliverability is checked
    # via the verification email, not here.
    email: EmailStr
    # 8 char min is NIST SP 800-63B guidance floor. Max 128 prevents bcrypt
    # DoS (bcrypt hashes up to 72 bytes anyway; longer is wasted CPU and
    # can be used to slow the server with giant inputs).
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class VerifyEmailIn(BaseModel):
    token: str = Field(min_length=16, max_length=256)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResendVerificationIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)


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
