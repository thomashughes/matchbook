# Matchbook v2

Multi-user, AI-powered job matching platform. Scores candidates against job listings, generates cover letters, prepares interview materials, and tracks the whole job-search pipeline.

**Showcase piece** — code is heavily commented throughout so every architectural decision can be explained in a live review. Comments are a deliverable, not an afterthought.

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript + Vite, Tailwind, Zustand, TanStack Query |
| Backend | FastAPI (Python 3.12), SQLAlchemy 2.0 async, Alembic |
| Database | PostgreSQL 16 |
| Cache / rate limit | Redis 7 |
| AI | Anthropic Claude (`claude-sonnet-4-5`) |
| Auth | RS256 JWT (15-min access, in-memory) + 7-day refresh in httpOnly cookie |
| Containerisation | Docker Compose |

## Local development

```bash
# 1. Generate JWT keypair (one-time)
mkdir -p backend/keys
openssl genrsa -out backend/keys/jwt_private.pem 2048
openssl rsa -in backend/keys/jwt_private.pem -pubout -out backend/keys/jwt_public.pem

# 2. Generate a Fernet key for encrypting OAuth tokens at rest
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Paste into .env as FERNET_KEY

# 3. Configure environment
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY, SMTP creds, Google OAuth creds

# 4. Boot everything
docker compose up --build
```

- Frontend: http://localhost:3085
- API: http://localhost:3086/api/v1
- API docs: http://localhost:3086/docs

## Project layout

```
matchbook-v2/
├── frontend/           React + Vite
├── backend/            FastAPI + SQLAlchemy + Alembic
├── browser-extension/  Chrome MV3 + Firefox port (Phase 4)
├── docker-compose.yml
└── .github/workflows/  CI/CD (Phase 5)
```

## Build phases

See `matchbook_v2_handoff.docx` for the full spec.

- **Phase 1 — Foundation** (current): Docker stack, DB schema + migrations, auth endpoints with rate limiting, frontend auth pages.
- Phase 2 — Core product: CV parse, onboarding, job scoring, dashboard.
- Phase 3 — AI features: cover letters, interview prep, company research, compare.
- Phase 4 — Integrations: Google Calendar, file uploads, browser extension.
- Phase 5 — Polish: CI/CD, Apache vhost, empty/loading/error states, final comment pass.
