# Matchbook v2 — handoff

**Timestamp:** 2026-04-16 (continuation of 2026-04-15 session)
**Branch:** feature/multi-tenant (working in /Users/thomashughes/Desktop/Projects/matchbookv2)
**Phase status:** Phase 1 ✅ · Phase 2 ✅ (verified end-to-end by user) · Phase 3 in progress — **2 of 6 AI actions shipped**.

Read `CLAUDE.md` in the repo root first. Run docker/compose yourself — never ask the user to paste output.

## Current state

All four containers were up at handoff time. Verify with `docker compose ps` before doing anything:

- `matchbookv2-backend-1`   → 3086 (most recent rebuild applied migration `0002_job_ai_outputs`)
- `matchbookv2-frontend-1`  → 3085
- `matchbookv2-postgres-1`  → healthy
- `matchbookv2-redis-1`     → healthy

User has a verified account + populated profile + at least one scored job + one cover letter (v1) already in the DB from last session's testing. Treat that data as real — don't wipe it.

## Phase 3 AI-action roadmap (user-agreed order)

1. ✅ **Cover letter** — own table (`cover_letters`), own routes (`/jobs/{id}/cover-letters`), panel on JobDetailPage. Shipped + user-verified.
2. ✅ **Outreach** — generic `job_ai_outputs` table, route `POST /jobs/{id}/ai-outputs/outreach`, `OutreachPanel`. Shipped **in this session** — user will test next.
3. ⏳ **Form response** (paste a question from an application form → tailored answer). Next up.
4. ⏳ **Follow-up** message.
5. ⏳ **Interview prep** (technical / behavioural / questions to ask).
6. ⏳ **Company research** (needs web-search tool; `company_research_cache` table already exists from Phase 1 schema).

Each saves per-job version history. Collapsible version cards, only latest auto-open, copy + delete per version — same pattern across all panels.

## What shipped in the last session (2026-04-15 → 2026-04-16)

### Phase 2 polish (user-verified, working)
- AILoadingSteps rewritten: one step at a time, fade in/out, Sparkles pulses through the fade, aria-live polite.
- "Build my profile" button shows Loader2 + "Building…" while `useSubmitAnswers` is pending.
- Optional "anything else?" free-text appended to onboarding Q&A (bumped `AnswersIn.max_length` 10 → 12).
- RAG score colours via `scoreColour(pct)` = `hsl(pct * 130, 65%, 42%)` in `ScoreRing.tsx`. Exported + reused elsewhere.
- StatusBadge distinct colours: saved=parchment, applied=gold-light, interviewing=#dbe7f3/#2b5d89, offer=teal-light, rejected=rust-light. Status buttons on JobDetailPage reuse the same palette via an `activeCls` record so selection reads identically everywhere.
- `_score_and_persist` in `routes/jobs.py` now writes Claude-extracted `title`/`company`/`location` back onto the job row (overwriting "Untitled role"/"Unknown company" fallbacks).
- `RequireProfile` wrapper in `App.tsx` redirects to `/onboarding/cv` when `useProfile()` is in error state (handles 404 = no profile yet).

### Phase 3 — Cover letter (user-verified)
- `backend/app/prompts/cover_letter.py` — tone × length matrix + SYSTEM + `build_user_message`.
- `backend/app/schemas/cover_letters.py`, `backend/app/api/routes/cover_letters.py` (`POST`, `GET`, `DELETE`). `response_model=None` + explicit `Response(status_code=204)` on delete to satisfy FastAPI's 204 assertion.
- `complete_text()` helper in `ai_service.py` for plain-text outputs (no JSON overhead).
- `frontend/src/components/jobs/CoverLetterPanel.tsx` with segmented tone (Conversational/Formal) + length (Short/Standard/Detailed) controls and `LetterCard` version cards.

### Phase 3 — Outreach (code complete, awaiting user test)
- New model `app/models/job_ai_output.py` + re-export in `models/__init__.py`.
- Alembic `0002_job_ai_outputs` migration applied on backend rebuild (confirmed in logs).
- `app/prompts/outreach.py` — CHANNELS (linkedin_connection / linkedin_inmail / email), RECIPIENT_ROLES (hiring_manager / recruiter / team_member / referral), SYSTEM + `build_user_message`.
- `app/schemas/ai_outputs.py` — `OutreachGenerateIn`, `JobAIOutputOut`, `Kind` literal.
- `app/api/routes/ai_outputs.py` — `GET /jobs/{id}/ai-outputs?kind=…` (list all versions of one kind), `DELETE /jobs/{id}/ai-outputs/{output_id}` (shared across kinds), `POST /jobs/{id}/ai-outputs/outreach` (kind-specific so Pydantic validates the right knobs). Registered in `main.py`.
- Frontend: `OutreachChannel` / `OutreachRecipientRole` / `JobAIOutput` / `AIOutputKind` in `types/models.ts`; `useAIOutputs`, `useDeleteAIOutput`, `useGenerateOutreach` in `api/hooks.ts`.
- `components/jobs/OutreachPanel.tsx` — segmented channel + recipient role, optional name input, `OutreachCard` mirrors `LetterCard` exactly. Mounted in `JobDetailPage.tsx` between `<CoverLetterPanel />` and the Notes card.

### Deferred to "future features" memory (do NOT do these unless user asks)
Saved in `/Users/thomashughes/.claude/projects/-Users-thomashughes/memory/project_matchbookv2_future_features.md`:
- CV view / download / replace UI.
- Live job discovery via Claude web search (companies direct or job boards).
- Multiple profiles per user (different CVs for different role types).

## Architectural decisions worth preserving

- **Two tables for AI actions, not one.** Cover letters kept their own table (`cover_letters`) — they have a stable tone/length schema and were in prod before the generic pattern emerged. Outreach + future #3–#5 share `job_ai_outputs` with a `kind` discriminator and kind-specific params in JSONB. This avoids four near-duplicate tables for four very similar features, and lets #3–#5 land in a single route file each (prompt + schema + POST handler).
- **Kind-specific POST endpoints under a generic table.** `POST /jobs/{id}/ai-outputs/outreach` (not `POST /jobs/{id}/ai-outputs` with kind in body) — this keeps Pydantic validation specific per kind. GET + DELETE are generic.
- **`version` race is cosmetic.** `SELECT MAX(version)+1` can duplicate under concurrent generation; accepted in the model docstring. Worth knowing if you ever want to add `UNIQUE (job_id, kind, version)` — don't without thinking through the lock.
- **422 debugging.** `main.py` has a `RequestValidationError` handler that logs the request body + errors to `uvicorn.error`. Saved us from the "stuck on Almost done" bug (root cause: `max_length=10` rejected 11 answers silently). Keep it.
- **Claude model.** `claude-sonnet-4-5` via `ANTHROPIC_MODEL` env. JSON calls go through `complete_json` with schema injection into the system prompt. Plain-text calls (cover letter, outreach) go through `complete_text` with `max_tokens` cap (2048 for letters, 1024 for outreach).

## How to resume

1. `cd /Users/thomashughes/Desktop/Projects/matchbookv2`
2. `docker compose ps` — confirm all four Up.
3. Ask the user: did Outreach work end-to-end for you? Any copy/colour/UX feedback before we move on?
4. If green-lit → build **#3 Form response**. Plan:
   - Add `form_response` to the `Kind` literal (already in `schemas/ai_outputs.py`).
   - `app/prompts/form_response.py` — SYSTEM teaches Claude to answer ONE application-form question using only profile + JD facts, match the question's style (STAR / short / word-count bounded). Input schema: `question: str` + optional `max_words: int`.
   - `POST /jobs/{id}/ai-outputs/form-response` in `ai_outputs.py`.
   - `useGenerateFormResponse` hook.
   - `FormResponsePanel.tsx` — large textarea for the question (this is the one panel where input is the key control, not a segmented selector) + optional word-count number input + Generate. Version cards show a truncated question preview in the chip row.
   - Slot into `JobDetailPage.tsx` between OutreachPanel and Notes. Order so far: score → explanations → status → CoverLetter → Outreach → FormResponse → Notes → raw JD.
5. After #3 lands, #4 (follow-up) and #5 (interview prep) are the same template — one prompt + one route handler + one panel each.
6. **#6 Company research** needs Claude web search turned on. Check `app/services/ai_service.py` for whether tool use is wired; existing `company_research_cache` table takes `research_data JSONB` — treat it as a cache-aside (hit cache first, fall through to Claude + cache, expire via `expires_at`).

## Commands you'll use

- Backend change: `docker compose up -d --build backend` → check `docker compose logs --tail=40 backend` (migrations run on start).
- Frontend change: `docker compose up -d --build frontend` — TS errors fail the build silently in `-d`; run `docker compose build frontend` (foreground) if you suspect type drift.
- Inspect DB: `docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB`.
- Tail backend live: `docker compose logs -f backend`.

## Rules carried over (graded deliverables — do not skip)

- Every non-trivial function/decision gets a WHAT + WHY comment. Portfolio-graded.
- Warm Modern tokens only via `mb-*` utility classes in `globals.css`. RAG ring via `scoreColour()`.
- No tokens in localStorage. Access = Zustand-in-memory, refresh = httpOnly cookie path-scoped to `/auth`.
- `/jobs/compare` must stay declared **before** `/jobs/{job_id}` in `routes/jobs.py`.
- Job list endpoint uses a batched latest-scores fetch — don't reintroduce N+1.
- `/jobs/{id}/ai-outputs/{output_id}` DELETE must stay under the generic router for all future kinds.
- Version cards: only latest auto-opens; copy with Check confirmation; delete with confirm UX where destructive.
