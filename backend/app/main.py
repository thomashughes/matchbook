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
from app.api.routes import company_research as company_research_routes
from app.api.routes import cover_letters as cover_letters_routes
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    # Required for the refresh cookie to be sent on /auth/refresh from
    # the frontend origin.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.exception_handler(RequestValidationError)
async def _log_validation_errors(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Log the actual body + errors on 422 so we can diagnose client/server
    schema drift instead of staring at opaque 'Unprocessable Entity' lines."""
    try:
        body = await request.body()
        body_preview = body.decode("utf-8")[:2000]
    except Exception:
        body_preview = "<unreadable>"
    logging.getLogger("uvicorn.error").warning(
        "422 on %s %s | errors=%s | body=%s",
        request.method,
        request.url.path,
        _json.dumps(exc.errors(), default=str)[:1500],
        body_preview,
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.get("/healthz", tags=["meta"])
async def healthz() -> dict[str, str]:
    """Liveness probe.

    Deliberately simple: it does NOT check the DB. A DB outage should
    NOT cause Docker to restart the API — restarting won't fix the DB
    and will just spam logs. Readiness (which does check the DB) is a
    separate Phase-5 endpoint for orchestrators that support it.
    """
    return {"status": "ok"}
