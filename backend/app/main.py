"""
FastAPI app entry point.

Startup order:
    Alembic migrations run in the Dockerfile CMD *before* uvicorn — so by
    the time this module imports, the DB schema is up to date. We do NOT
    run migrations from Python here because a failed migration should
    prevent the API from starting at all (fail-loud on schema drift).

CORS:
    Locked to the domains in settings.CORS_ORIGINS. Credentials are
    enabled because /auth/refresh relies on a cookie being sent.
    Wildcard origins with credentials is a spec violation and a security
    hazard — we never do it.
"""

import logging
import json as _json

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import ai_outputs as ai_outputs_routes
from app.api.routes import auth as auth_routes
from app.api.routes import billing as billing_routes
from app.api.routes import company_research as company_research_routes
from app.api.routes import cover_letters as cover_letters_routes
from app.api.routes import cv as cv_routes
from app.api.routes import dashboard as dashboard_routes
from app.api.routes import jobs as jobs_routes
from app.api.routes import profile as profile_routes
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Matchbook API",
    version="2.0.0",
    # All routes live under /api/v1. Apache proxies /api → this service,
    # so /api/v1/auth/login is the externally visible path.
    root_path="",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
)

# Hard cap on request body size, enforced before route code runs. This
# mirrors the nginx client_max_body_size 10m so a request that bypasses
# the proxy (someone hitting :3086 directly on the host, or a future
# misconfig) still can't post a gigabyte of garbage and OOM the worker.
# CV upload (the largest legitimate body) tops out at ~5MB, so 10MB has
# plenty of headroom. Returns 413 with no body parse — the request
# stream is never read.
_MAX_REQUEST_BYTES = 10 * 1024 * 1024


@app.middleware("http")
async def _enforce_max_body_size(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > _MAX_REQUEST_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large."},
                )
        except ValueError:
            # Malformed Content-Length — let the framework reject it.
            pass
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    # Required for the refresh cookie to be sent on /auth/refresh from
    # the frontend origin.
    allow_credentials=True,
    # Pinned to actual usage rather than "*". With allow_credentials=True
    # the spec disallows wildcards anyway (browsers reject the response),
    # but Starlette papers over that by echoing the request's method/headers
    # — which is functionally equivalent to a wildcard. Listing them
    # explicitly makes the contract obvious to a reader and removes the
    # surface for header-based gadget attacks.
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)

# Versioned prefix — means a v2 of the API can be introduced without
# breaking existing clients by mounting another router alongside.
API_V1 = "/api/v1"
app.include_router(auth_routes.router, prefix=API_V1)
app.include_router(profile_routes.router, prefix=API_V1)
app.include_router(jobs_routes.router, prefix=API_V1)
app.include_router(cover_letters_routes.router, prefix=API_V1)
app.include_router(ai_outputs_routes.router, prefix=API_V1)
app.include_router(company_research_routes.router, prefix=API_V1)
app.include_router(billing_routes.router, prefix=API_V1)
app.include_router(cv_routes.router, prefix=API_V1)
app.include_router(dashboard_routes.router, prefix=API_V1)


# Paths whose request bodies must NEVER be logged because they carry
# plaintext credentials, reset tokens, or other secrets. Pydantic's 422
# fires *before* the route runs, so a malformed payload (bad email format,
# extra unknown field, etc.) would otherwise dump the password into the
# logs at WARNING level.
_SENSITIVE_PATH_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/billing/webhook",
)


def _is_sensitive_path(path: str) -> bool:
    return any(path.startswith(p) for p in _SENSITIVE_PATH_PREFIXES)


@app.exception_handler(RequestValidationError)
async def _log_validation_errors(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Log errors on 422 so we can diagnose client/server schema drift.

    The request body is logged for non-sensitive paths only — auth and
    webhook bodies carry secrets (passwords, reset tokens, signing
    payloads) that must never reach the log stream. For those paths we
    log just the error structure, which is enough to identify the
    malformed field without exposing its value.
    """
    path = request.url.path
    if _is_sensitive_path(path):
        body_preview = "<redacted: sensitive path>"
    else:
        try:
            body = await request.body()
            body_preview = body.decode("utf-8")[:2000]
        except Exception:
            body_preview = "<unreadable>"
    # Pydantic v2 may surface the original Python exception inside the
    # error's `ctx` field, which json.dumps can't serialise without help.
    # Round-trip through default=str so the response is always emittable.
    safe_errors = _json.loads(_json.dumps(exc.errors(), default=str))
    logging.getLogger("uvicorn.error").warning(
        "422 on %s %s | errors=%s | body=%s",
        request.method,
        path,
        _json.dumps(safe_errors)[:1500],
        body_preview,
    )
    return JSONResponse(status_code=422, content={"detail": safe_errors})


@app.get("/healthz", tags=["meta"])
async def healthz() -> dict[str, str]:
    """Liveness probe.

    Deliberately simple: it does NOT check the DB. A DB outage should
    NOT cause Docker to restart the API — restarting won't fix the DB
    and will just spam logs. Readiness (which does check the DB) is a
    separate Phase-5 endpoint for orchestrators that support it.
    """
    return {"status": "ok"}
