# CLAUDE.md

Claude: you have a Bash tool. Run docker/compose commands yourself — don't ask the user to run them and paste output. After any code change, rebuild and check logs before declaring the task done.

## Running the project
- All services run via Docker Compose from repo root
- Start everything: `docker compose up -d` (always detached — never foreground, it blocks the terminal)
- View logs: `docker compose logs --tail=100 <service>`
- Restart a service: `docker compose restart <service>`
- Rebuild after code changes: `docker compose up -d --build <service>`
- Stop everything: `docker compose down` (keeps volumes); `down -v` wipes the DB

## Services
- frontend — React/Nginx on port 3085 (production build inside the image — no HMR)
- backend  — FastAPI on port 3086
- postgres — on 5432, internal only
- redis    — on 6379, internal only

## After changing code — always
- **Frontend TS/TSX/CSS change:** `docker compose up -d --build frontend` (Vite rebuilds inside image). TS errors fail the build — read the compose output.
- **Backend Python change:** `docker compose up -d --build backend` (also re-runs `alembic upgrade head` on start).
- **New Alembic migration:** rebuild backend; check logs for migration output.
- **nginx.conf change:** rebuild frontend.
- **docker-compose.yml / .env change:** `docker compose up -d` (recreates affected services).
- **Frontend package.json change:** rebuild frontend (npm install runs in the build stage).
- **Backend requirements.txt change:** rebuild backend.

## When something's broken — standard triage order
1. `docker compose ps` — is everything `Up (healthy)`? A `Restarting` container = crash loop, go to logs.
2. `docker compose logs --tail=80 <service>` — read the actual error. Don't guess.
3. Hit `http://localhost:3086/healthz` to confirm backend is reachable from host.
4. `docker compose exec backend python -c "..."` to poke at state inside the container.
5. `docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB` for DB queries.

## Common failure signatures
- **502 Bad Gateway from frontend:** backend is down or crash-looping. Check `docker compose ps` + backend logs.
- **CORS / "not allowed" / HTML where JSON expected:** nginx isn't proxying `/api/` — check `frontend/nginx.conf`.
- **Register/login "something went wrong":** usually backend 500 — check backend logs, not the browser.
- **`postgres` won't start, ICU locale error:** use `postgres:16` (Debian), not `-alpine`. Wipe with `docker compose down -v` if volume is corrupted.
- **Frontend TS build fails:** TS errors don't show in `compose up -d` — run `docker compose logs --tail=200 frontend` or `docker compose build frontend` (foreground) to see them.

## Port conflicts
`lsof -i :3085` or `:3086` — find what's holding the port.

## Never do
- Do not run on ports 4000 or 3069 (other projects).
- Do not drop the database (`down -v`, `DROP TABLE`, migration downgrade) without explicit confirmation.
- Do not run `docker compose up` foreground — always `-d`, otherwise the shell blocks.
- Do not skip the rebuild after code changes. Source isn't bind-mounted; the image is the source of truth.
- Do not commit `.env`, `backend/keys/`, or `uploads_data/`.

## Secrets & env
- `.env` at repo root (gitignored) — DB creds, JWT paths, Fernet key, Anthropic key, SMTP.
- `backend/keys/jwt_private.pem` + `jwt_public.pem` — RS256 keypair, mounted read-only into the container.
- In dev, SMTP is usually unconfigured: the backend prints verification/reset links to stdout. Look in backend logs after register.

## Code conventions (graded — don't skip)
- Every non-trivial function/decision gets a WHAT + WHY comment. Single-line file-top docstrings are fine for trivial UI components; anything with logic gets more.
- Frontend tokens live in `frontend/src/styles/globals.css` (Warm Modern palette — cream/rust/teal/gold/ink). Use `mb-*` utility classes, not raw colours.
- Backend: async SQLAlchemy 2.0 everywhere, Pydantic v2 schemas, routes under `/api/v1`.
- Job list endpoint uses a batched latest-scores fetch — don't reintroduce N+1 when editing it.
- `/jobs/compare` must be declared **before** `/jobs/{job_id}` or FastAPI captures "compare" as a UUID.
