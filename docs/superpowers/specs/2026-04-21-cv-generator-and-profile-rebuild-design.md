# CV Generator + Profile Rebuild — Design Spec

**Date:** 2026-04-21
**Status:** Design approved, ready to build
**Scope:** New feature (AI CV Builder) + one existing-feature improvement (Profile Rebuild) + small UX fixes (upload affordance).

---

## 1. Motivation

A candidate's CV is the single biggest lever on whether they get an interview. Thomas has independently refined a two-phase prompt that produces CVs without the usual AI-jargon tells ("leverage", "tapestry", em-dashes, triplet structures). This prompt has been validated repeatedly in conversations and has driven real interview outcomes. Porting it into Matchbook turns it into a repeatable paid product rather than a one-off artefact.

Complementary to that: users can get stuck mid-onboarding or want to start over with a different target role. Today the only path is deleting the account. A "rebuild" flow respects the effort they've already put in (keep their saved jobs) while letting them refresh the foundation (re-upload CV, re-answer questions).

## 2. Scope

### In scope
- CV generator feature, paid-only, 2/billing cycle.
- Two-phase prompt flow (Claude generates questions, user answers, Claude rewrites).
- Inline rich-text editor using Markdown under the hood, TipTap on the surface.
- Neutral, classic CV PDF export — no Matchbook branding on the output.
- Markdown source download alongside PDF.
- Version history mirroring cover-letter UX (keep AI-generated versions; edits overwrite current version).
- Regenerate flow: user must explain *why* before spending a credit; shown the quota remaining and a hallucination warning.
- Tone selector (professional / bold) at Phase 2 trigger.
- `[VERIFY: …]` inline badges rendered as first-class UI so the user cannot miss them.
- `[REWRITE: …]` "Why this change?" inline badges — short Claude-written rationale tied to specific lines.
- Word-count cue on Phase 2 output with a 400/1000 warning band.
- Scroll-to-top on Phase 2 completion.
- Profile rebuild: POST /profile/rebuild, profile versioning, stale-score banners on jobs, stale-source flag on existing cover-letters and CV versions.
- "Continue onboarding" button in the top bar, visible only to users who haven't completed onboarding.
- Drag-and-drop on the CV upload field.
- "PDF or Word documents only" hint on the upload field.

### Out of scope
- DOCX export (PDF only for v1).
- Anonymous shareable CV links.
- Multi-CV support (one "current CV" with version history).
- Per-job CV tailoring (v2 idea: generate a CV specifically for one job).
- Vision-OCR fallback for image-scanned CV uploads (already explicitly deferred in existing cv_parser.py).

## 3. Data model

### New: `cv_versions` table
One row per AI-generated CV version. Mirrors the shape of `cover_letters`.

| Column                       | Type          | Notes                                                              |
| ---------------------------- | ------------- | ------------------------------------------------------------------ |
| id                           | UUID pk       |                                                                    |
| user_id                      | UUID fk users | Tenant isolation.                                                  |
| version                      | int           | Monotonic per user. max+1 on create.                               |
| content_markdown             | text          | Full CV in Markdown.                                               |
| tone                         | text          | 'professional' or 'bold'.                                          |
| questions_payload            | jsonb         | Full Phase-1 questions + user answers, for audit.                  |
| regenerate_reason            | text null     | Reason the user gave when regenerating; null on first generation.  |
| profile_version              | int           | Snapshot of profile version at generation time (see rebuild flow). |
| created_at                   | timestamptz   | Server-set.                                                        |

### Change: `users` gains `profile_version`
Int, default 1, NOT NULL. Incremented on every `/profile/rebuild`. Used to compare with `profile_version` stored on dependent artefacts (jobs, cvs, cover-letters) to drive the stale banners.

### Change: `jobs` gains `scored_against_profile_version`
Int null. Set on every score. When it differs from `users.profile_version`, the UI shows the stale-score banner.

### Change: `cover_letters` gains `profile_version`
Int. Default 1 on existing rows (migration sets); set to current version on create going forward. Used to flag "generated against previous profile".

### Quota registry change: `RESOURCES` gets `cv_generation`
- Paid cap: 2/month.
- Free cap: 0.
- Scope: user-level (not per-job).
- Window: billing-cycle-aware. Already implemented in `current_window()`.

## 4. Backend

### New routes under `/api/v1/cv`

- `POST /cv/phase-one` — runs `complete_json` with the Phase-1 system prompt; returns structured question list (`[{id, text, type, hint, options?}]`). Does NOT consume a credit. Idempotent cache: same profile_version ⇒ same questions for 15min (Redis).
- `POST /cv/phase-two` — body: `{answers: [...], tone: 'professional'|'bold', regenerate_reason?: string}`. Consumes a credit via `Depends(entitlement("cv_generation"))`. Runs `complete_text` against Phase-2 prompt. Creates a `cv_versions` row. Wraps in refund-on-failure.
- `GET /cv` — list versions newest first.
- `GET /cv/{id}` — fetch one.
- `PUT /cv/{id}` — save inline edits. Body: `{content_markdown}`. Does NOT create a new version; updates in place. Timestamp updated.
- `DELETE /cv/{id}` — confirm-guarded at UI layer.
- `GET /cv/{id}/pdf` — renders Markdown → HTML → PDF via WeasyPrint. Response is `application/pdf` with `Content-Disposition: attachment; filename="..."`. No credit cost.
- `GET /cv/{id}/markdown` — raw download. No credit cost.

### New prompt module `app/prompts/cv_generator.py`
Two exports:
- `PHASE_ONE_SYSTEM` — the "senior talent agent" system prompt, modified to output structured JSON matching `Phase1Questions` schema instead of pipe-delimited text. **Change from user's prompt:** output is JSON, not `Q1: ... | type | hint`, so we can parse reliably without regex.
- `PHASE_TWO_SYSTEM` — the rewrite prompt, modified to output Markdown (`##` section headings, `**` bold, `- ` bullets) instead of "clean plain text". Also instructed to wrap uncertain facts in `[VERIFY: note]` and tag major changes with `[REWRITE: one-line rationale]`.

### New route `POST /api/v1/profile/rebuild`
- Deletes all `ProfileAnswer` rows for the user.
- Increments `users.profile_version`.
- Clears `profile.cv_raw_text`, `cv_file_path`, `structured_data`, typed fields.
- Keeps `jobs` and `cover_letters` and `cv_versions` rows intact — their stored `profile_version` column will now lag the user's current version, which the UI reads to show stale banners.
- Returns 204.

### PDF renderer
New module `app/services/cv_pdf.py` using WeasyPrint. HTML template at `app/services/cv_template.html` — minimal neutral styling: Georgia serif for body, Helvetica for headings, 11pt body / 16pt name / 12pt section headings, 1.15 line height, 20mm margins, A4. Nothing that says "generated by an app" — it should look like any candidate's CV.

WeasyPrint adds `weasyprint` to `requirements.txt`. Alternative considered: Playwright (needs a browser in the container — heavier). Rejected on container size grounds.

### Existing onboarding changes
- `GET /profile` response gains `onboarding_complete: bool` — derived from `structured_data.generated` presence. Frontend uses this to gate the "continue onboarding" button.

## 5. Frontend

### New page `CvBuilderPage.tsx` at `/cv`
Four states:
1. **Empty** — "You haven't generated a CV yet. Click Start." Upgrade prompt for free users.
2. **Phase 1** — questions rendered dynamically (text/textarea/radio based on type), tone selector (professional/bold radio buttons) at the end. "Anything else you'd like to include?" textarea is added by the UI as the final question, not requested from Claude.
3. **Generating** — spinner, progress copy ("Rewriting your CV — this takes ~30 seconds").
4. **Editor** — rich editor (TipTap + markdown extensions), sidebar lists versions (mirrors cover-letters version list with auto-open-latest + Check-on-copy + confirm-on-delete). Download PDF + Download Markdown buttons. `[VERIFY]` and `[REWRITE]` badges rendered via custom TipTap marks with hover tooltips.

### Menu icon
`FileText` Lucide icon labelled "CV" in `Sidebar.tsx`, positioned between Jobs and Billing.

### Regenerate modal
Opens when user clicks "Generate new version" in editor. Modal contents:
- Text: "You have X of 2 generations left this billing cycle."
- Text: "Claude can make mistakes. Always double-check names, dates, and anything marked [VERIFY]."
- Textarea: "What would you like different this time?" (required, min 20 chars). This becomes `regenerate_reason` on the cv_versions row and is prepended to the Phase-2 user message.
- Tone selector.
- Cancel / Generate buttons.

### Continue Onboarding button
New component `ContinueOnboardingBanner.tsx` in `TopBar.tsx`. Shows when `profile.onboarding_complete === false`. Clicking takes them to `/onboarding/questions` (if CV uploaded but answers not submitted) or `/onboarding/upload` (if no CV yet).

### Rebuild Profile button
In `ProfilePage.tsx`, new "Danger zone" section at the bottom: "Rebuild profile" button with confirm modal explaining existing jobs/CVs/cover-letters stay but get marked stale.

### Upload UX (CVUploadPage.tsx and any job-JD PDF upload)
- Drag-and-drop drop zone using native HTML5 drag events.
- Helper copy directly under file picker: "PDF or Word documents only, max 5MB."

### Stale banners
- On job detail page: if `job.scored_against_profile_version !== user.profile_version`, show yellow banner: "This score was based on a previous profile. Re-score to refresh."
- On cover-letter version card: if `cover_letter.profile_version !== user.profile_version`, small pill: "Previous profile".
- Same on CV version cards.

### Word count cue
Below editor: "XXX words — roughly N pages." Amber warning if <400 or >1000.

### Scroll-to-top
On Phase-2 success, `window.scrollTo({top:0, behavior:'smooth'})` before showing the editor.

## 6. Security & correctness rules

- All Claude calls go through `complete_json` or `complete_text` — never direct Anthropic SDK.
- Phase 1 system prompt: JSON schema returned; XML-wrap the parsed CV text.
- Phase 2 system prompt: plain text in, Markdown out. XML-wrap parsed CV + answers.
- PDF endpoint: markdown → HTML → PDF pipeline MUST escape HTML entities on the way in (use `markdown-it` with html:false). Never trust stored markdown to be HTML-safe.
- Refund-on-failure on Phase 2 route, per existing pattern.
- Rebuild cannot run during in-flight AI jobs — check no ai_output with created_at within last 30s. (Soft; avoids race where a score completes seconds after a rebuild using the old profile.)
- `cv_generation` quota is user-scoped. `scope_key = str(user.id)`. Matches existing `ai_job_search` pattern.

## 7. Rejected alternatives

- **Single generation per cycle.** Bad UX — one bad draft and they're stuck a month.
- **Unlimited edits + 1 AI generation per cycle.** Considered (option B in conversation). Rejected: 2/cycle matches the mental model users will have ("got one I don't love, got one more shot").
- **Pipe-delimited question output.** Thomas's original prompt uses `Q1: ... | type | hint`. Switched to JSON so we get Pydantic validation and reliable type routing (radio needs its `options` array). Prompt is updated accordingly in the new module; Thomas's original is preserved in this spec for record.
- **DOCX export.** High implementation cost (python-docx templates, plus maintaining separate styling). User opens the PDF in Preview, can Export to DOCX from there. Revisit only if users request.
- **"Clean plain text" as the CV format.** Rejected — incompatible with rich editor. Markdown does the same job and round-trips through TipTap cleanly.

## 8. Risks

- **TipTap bundle size.** Rich editors are heavy. Lazy-load the CV editor route via React.lazy so the main bundle isn't penalised for a feature most users don't use daily.
- **WeasyPrint font rendering in container.** Need to bundle Liberation Serif / DejaVu fonts in the backend image. If omitted, WeasyPrint falls back to pixelated text. Add to Dockerfile.
- **Hallucinations in CV content.** Core risk. Mitigations: `[VERIFY]` flags rendered prominently, warning copy shown on every generation and in the editor footer. Accept remaining risk — we're a tool, not a guarantor.
- **Phase 1 cached questions drift.** If we cache Phase 1 output in Redis and the user edits the profile in the interim, they'll get stale questions. Fix: cache key includes `profile.updated_at.isoformat()`.
- **PDF export rendering unicode correctly** — test with a CV containing a candidate's name using non-ASCII characters.

## 9. Rollout

1. Build behind a `VITE_FEATURE_CV_BUILDER` env flag so we can merge before enabling. Actually no — flag adds more complexity than it solves here; ship it directly. Users who don't click CV don't pay a cost.
2. Migration runs on deploy as usual. Zero backfill needed except `profile_version=1` everywhere.
3. First real user = Thomas; he verifies end-to-end on prod before announcing.

## 10. Open questions (none blocking)

- Should version history have names ("CV – April 2026" vs. "CV version 3")? Decision: version numbers only to start; auto-name is noise.
- Should the editor auto-save? Decision: explicit Save button, matching cover letter UX.
