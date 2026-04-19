# Matchbook v2 backend — FastAPI on Python 3.12.
#
# Multi-stage build is overkill for a Python app (no compile step like Go/Rust),
# so we use a single slim base. We do pay attention to layer ordering: copy
# requirements.txt first so `pip install` caches independently of app code.
# A one-line change to app/ won't invalidate the dependency layer.

FROM python:3.12-slim

# libmagic1 → python-magic reads file signature bytes for upload validation
#             (the "PDF/Word only" rule can't trust Content-Type or extension).
# build-essential + libpq-dev → psycopg2 (used by Alembic sync) needs libpq headers.
# curl → container healthchecks and debugging.
# Clean the apt lists in the same RUN so they don't bloat the image layer.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependency layer — changes rarely, stays cached across code edits.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application layer — changes often.
COPY . .

# uvicorn is the ASGI server. --host 0.0.0.0 so the container is reachable
# from outside, --reload is OFF in the image; dev uses a compose override
# or `docker compose run` with a bind mount to enable reload.
#
# The startup script runs migrations before booting the API so a fresh
# database (or one pending a new migration) self-heals on deploy.
CMD ["/bin/bash", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
