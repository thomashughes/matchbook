# Matchbook v2 backend — FastAPI on Python 3.12.
#
# Multi-stage:
#   1. `builder` installs build toolchain + headers, compiles wheels for any
#      C-extension deps (psycopg2 against libpq), and produces a /wheels dir.
#   2. `runtime` only ships the runtime libs + the pre-built wheels — no
#      compiler, no headers, no apt cache. Removes ~250MB of post-RCE attack
#      surface (gcc, ld, dpkg-dev, etc.).
#
# The runtime image runs as a non-root user (appuser, uid 1000) so even an
# RCE inside uvicorn doesn't get root inside the container.

# --- Stage 1: builder ------------------------------------------------------
FROM python:3.12-slim AS builder

# build-essential + libpq-dev are only needed to compile psycopg2.
# Neither leaves this stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
# `pip wheel` emits a wheel per dep into /wheels. The runtime stage installs
# from that directory with --no-index so it never has to compile anything.
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# --- Stage 2: runtime ------------------------------------------------------
FROM python:3.12-slim

# Runtime-only OS deps. Notably NO build-essential / libpq-dev / gcc.
# libmagic1 → python-magic reads file signature bytes for upload validation
#             (the "PDF/Word only" rule can't trust Content-Type or extension).
# libpq5 → psycopg2 wheel needs libpq.so.5 to load at runtime.
# curl → container healthchecks and debugging.
# libpango / libcairo / libgdk-pixbuf / shared-mime-info → WeasyPrint runtime
#   for the CV PDF exporter. Without these the import succeeds but rendering
#   blows up at request time with a CFFI error.
# fonts-liberation / fonts-dejavu → serif + sans-serif families with wide
#   Unicode coverage. Without them WeasyPrint falls back to pixelated glyphs
#   or skips non-ASCII characters silently, producing a broken CV.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    libpq5 \
    curl \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    fonts-liberation \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

# Non-root user. uid 1000 matches the conventional first non-system user.
# /var/matchbook/uploads is pre-created and chowned so the named volume
# inherits correct ownership on first mount (Docker copies image perms
# into a fresh empty volume).
RUN groupadd --system --gid 1000 appgroup \
    && useradd --system --uid 1000 --gid appgroup --shell /usr/sbin/nologin --create-home appuser \
    && mkdir -p /var/matchbook/uploads \
    && chown -R appuser:appgroup /var/matchbook

WORKDIR /app

# Install the pre-built wheels from the builder stage.
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links /wheels -r requirements.txt \
    && rm -rf /wheels

# Application layer — changes often.
COPY --chown=appuser:appgroup . .

USER appuser

# uvicorn is the ASGI server. --host 0.0.0.0 so the container is reachable
# from outside, --reload is OFF in the image; dev uses a compose override
# or `docker compose run` with a bind mount to enable reload.
#
# The startup script runs migrations before booting the API so a fresh
# database (or one pending a new migration) self-heals on deploy.
CMD ["/bin/bash", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
