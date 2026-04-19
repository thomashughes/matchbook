# JobDetailPage Collapsible AI Panels — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse all six AI panels on `JobDetailPage` by default, each header showing a one-line content-state hint. Notes card and raw JD disclosure remain untouched.

**Architecture:** One new shared `CollapsibleSection` component owns the `mb-card` chrome + header button + chevron. Each of the six panels is refactored to drop its self-wrapping `mb-card` and wrap its body in `CollapsibleSection` instead, computing its hint from its existing React Query hook. No new hooks, no lifted state, no persistence layer.

**Tech Stack:** React 18 + TypeScript + Tailwind tokens (`mb-*`) + `lucide-react` icons. Frontend builds inside the Docker image (no HMR). Backend is untouched.

**Workflow note:** This repo has no commits yet and the user tests locally before committing. Each task ends with code applied, no `git` steps. The final task rebuilds the frontend image once and runs a browser verification pass.

**Spec reference:** `docs/superpowers/specs/2026-04-17-jobdetail-collapsible-ai-panels-design.md`

---

## File structure

**Create:**
- `frontend/src/components/ui/CollapsibleSection.tsx` — shared wrapper, ~40 LOC

**Modify:**
- `frontend/src/components/jobs/CoverLetterPanel.tsx` — drop outer `mb-card`, wrap in CollapsibleSection, compute hint
- `frontend/src/components/jobs/OutreachPanel.tsx` — same pattern
- `frontend/src/components/jobs/FormResponsePanel.tsx` — same pattern
- `frontend/src/components/jobs/FollowUpPanel.tsx` — same pattern
- `frontend/src/components/jobs/InterviewPrepPanel.tsx` — same pattern
- `frontend/src/components/jobs/CompanyResearchPanel.tsx` — same pattern, plus export `relTime` for header hint use, and restructure the early `isLoading` return

**Unchanged:**
- `frontend/src/pages/JobDetailPage.tsx` — the panel call sites stay identical; each panel self-wraps in CollapsibleSection.

---

### Task 1: Create the shared CollapsibleSection component

**Files:**
- Create: `frontend/src/components/ui/CollapsibleSection.tsx`

- [ ] **Step 1: Write the component**

Write `frontend/src/components/ui/CollapsibleSection.tsx`:

```tsx
/**
 * CollapsibleSection — shared card wrapper with a click-to-expand header.
 *
 * Owns the `mb-card` chrome and the header button/chevron so every AI
 * panel on JobDetailPage renders with identical collapsed/expanded
 * affordances. Open state is local only — navigating away and back
 * resets to defaultOpen, which is intentional (spec: no persistence).
 *
 * The header is a native <button> so keyboard users get Tab + Space/Enter
 * toggling and screen readers see aria-expanded. Actions inside the
 * panel body (Generate / Copy / Delete) live as siblings of the header,
 * not nested inside it, so they don't inherit the toggle click.
 */
import { useState } from 'react';
import { ChevronDown } from 'lucide-react';

export function CollapsibleSection({
  title,
  hint,
  defaultOpen = false,
  children,
}: {
  title: string;
  hint?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="mb-card">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 text-left"
      >
        <ChevronDown
          size={16}
          className={`text-ink-3 transition-transform ${open ? '' : '-rotate-90'}`}
        />
        <span className="mb-display text-lg flex-1">{title}</span>
        {hint !== undefined && hint !== null && (
          <span className="text-xs text-ink-3">{hint}</span>
        )}
      </button>
      {open && <div className="mt-4">{children}</div>}
    </div>
  );
}
```

- [ ] **Step 2: Verify the file compiles (static check only)**

Nothing runs yet — Task 8 rebuilds everything. Just confirm the new file exists:

```bash
ls -la /Users/thomashughes/Desktop/Projects/matchbookv2/frontend/src/components/ui/CollapsibleSection.tsx
```

Expected: file exists, non-empty.

---

### Task 2: Refactor CoverLetterPanel

**Files:**
- Modify: `frontend/src/components/jobs/CoverLetterPanel.tsx`

- [ ] **Step 1: Add the CollapsibleSection import**

Change the import block at the top. Find:

```tsx
import { useState } from 'react';
import { Check, ChevronDown, Copy, Loader2, Sparkles, Trash2 } from 'lucide-react';
import {
  useCoverLetters,
  useDeleteCoverLetter,
  useGenerateCoverLetter,
} from '@/api/hooks';
```

Replace with:

```tsx
import { useState } from 'react';
import { Check, ChevronDown, Copy, Loader2, Sparkles, Trash2 } from 'lucide-react';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';
import {
  useCoverLetters,
  useDeleteCoverLetter,
  useGenerateCoverLetter,
} from '@/api/hooks';
```

- [ ] **Step 2: Replace the outer wrapper and title row with CollapsibleSection**

Find the `return (` block starting with `<div className="mb-card">`. Replace the full `return (...)` block in `CoverLetterPanel(...)` (roughly lines 52–149) with:

```tsx
  const count = letters.length;
  const hint = list.isLoading
    ? 'Loading…'
    : count === 0
      ? 'Not yet generated'
      : `${count} version${count === 1 ? '' : 's'}`;

  return (
    <CollapsibleSection title="Cover letter" hint={hint}>
      {/* Controls */}
      <div className="flex flex-wrap gap-4 mb-4">
        <div>
          <div className="mb-label mb-1">Tone</div>
          <div className="inline-flex rounded-full bg-parchment p-0.5">
            {TONES.map((t) => (
              <button
                key={t.value}
                onClick={() => setTone(t.value)}
                className={`px-3 py-1 text-xs rounded-full transition ${
                  tone === t.value ? 'bg-ink text-white' : 'text-ink-2'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="mb-label mb-1">Length</div>
          <div className="inline-flex rounded-full bg-parchment p-0.5">
            {LENGTHS.map((l) => (
              <button
                key={l.value}
                onClick={() => setLength(l.value)}
                className={`px-3 py-1 text-xs rounded-full transition ${
                  length === l.value ? 'bg-ink text-white' : 'text-ink-2'
                }`}
              >
                {l.label}
              </button>
            ))}
          </div>
        </div>

        <div className="ml-auto self-end">
          <button
            className="mb-btn-primary flex items-center gap-2"
            onClick={() => generate.mutate({ tone, length })}
            disabled={generate.isPending}
          >
            {generate.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Sparkles size={14} />
            )}
            {generate.isPending
              ? 'Writing…'
              : letters.length === 0
                ? 'Generate'
                : 'Generate another'}
          </button>
        </div>
      </div>

      {/* Empty state */}
      {letters.length === 0 && !generate.isPending && (
        <p className="text-sm text-ink-3">
          Generate a cover letter tailored to this role using your profile.
          Each click saves a new version.
        </p>
      )}

      {/* Version list */}
      {letters.length > 0 && (
        <div className="space-y-3">
          {letters.map((l, i) => (
            <LetterCard
              key={l.id}
              letter={l}
              defaultOpen={i === 0}
              onDelete={() => remove.mutate(l.id)}
            />
          ))}
        </div>
      )}

      {/* Surface any generation error inline so failed calls don't go
          silent. The standard case is a 429 from the rate limiter. */}
      {generate.isError && (
        <p className="text-sm text-rust mt-3">
          Couldn't generate — please try again in a moment.
        </p>
      )}
    </CollapsibleSection>
  );
```

Key differences from the current code:
- Outer `<div className="mb-card">` and closing `</div>` are gone — `CollapsibleSection` provides the card.
- The header row `<div className="flex items-center justify-between mb-3">…</div>` and its inline "Cover letter" title + version chip are deleted — the wrapper renders the title and the new `hint` takes the chip's role.
- Everything else inside the panel (controls, empty state, version list, error message) is preserved verbatim.
- The `LetterCard` inner component is NOT modified — it still handles per-version collapse and lives below the wrapper's expanded body.

---

### Task 3: Refactor OutreachPanel

**Files:**
- Modify: `frontend/src/components/jobs/OutreachPanel.tsx`

- [ ] **Step 1: Add the import**

Find:

```tsx
import { useState } from 'react';
import { Check, ChevronDown, Copy, Loader2, Send, Trash2 } from 'lucide-react';
import {
  useAIOutputs,
  useDeleteAIOutput,
  useGenerateOutreach,
} from '@/api/hooks';
```

Replace with:

```tsx
import { useState } from 'react';
import { Check, ChevronDown, Copy, Loader2, Send, Trash2 } from 'lucide-react';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';
import {
  useAIOutputs,
  useDeleteAIOutput,
  useGenerateOutreach,
} from '@/api/hooks';
```

- [ ] **Step 2: Replace the outer wrapper and title row**

Replace the `return (` block in `OutreachPanel(...)` (roughly lines 53–161) with:

```tsx
  const count = messages.length;
  const hint = list.isLoading
    ? 'Loading…'
    : count === 0
      ? 'Not yet generated'
      : `${count} version${count === 1 ? '' : 's'}`;

  return (
    <CollapsibleSection title="Outreach" hint={hint}>
      <div className="flex flex-wrap gap-4 mb-4">
        <div>
          <div className="mb-label mb-1">Channel</div>
          <div className="inline-flex rounded-full bg-parchment p-0.5">
            {CHANNELS.map((c) => (
              <button
                key={c.value}
                onClick={() => setChannel(c.value)}
                className={`px-3 py-1 text-xs rounded-full transition ${
                  channel === c.value ? 'bg-ink text-white' : 'text-ink-2'
                }`}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="mb-label mb-1">Recipient</div>
          <div className="inline-flex rounded-full bg-parchment p-0.5">
            {ROLES.map((r) => (
              <button
                key={r.value}
                onClick={() => setRole(r.value)}
                className={`px-3 py-1 text-xs rounded-full transition ${
                  role === r.value ? 'bg-ink text-white' : 'text-ink-2'
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 min-w-[180px]">
          <div className="mb-label mb-1">Name (optional)</div>
          <input
            value={recipientName}
            onChange={(e) => setRecipientName(e.target.value)}
            placeholder="e.g. Priya Patel"
            className="mb-input py-1 text-sm"
          />
        </div>

        <div className="self-end">
          <button
            className="mb-btn-primary flex items-center gap-2"
            onClick={() =>
              generate.mutate({
                channel,
                recipient_role: role,
                recipient_name: recipientName.trim() || null,
              })
            }
            disabled={generate.isPending}
          >
            {generate.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
            {generate.isPending
              ? 'Drafting…'
              : messages.length === 0
                ? 'Draft message'
                : 'Draft another'}
          </button>
        </div>
      </div>

      {messages.length === 0 && !generate.isPending && (
        <p className="text-sm text-ink-3">
          Draft a tailored message to a hiring contact — each click saves
          a new version you can copy and edit before sending.
        </p>
      )}

      {messages.length > 0 && (
        <div className="space-y-3">
          {messages.map((m, i) => (
            <OutreachCard
              key={m.id}
              output={m}
              defaultOpen={i === 0}
              onDelete={() => remove.mutate(m.id)}
            />
          ))}
        </div>
      )}

      {generate.isError && (
        <p className="text-sm text-rust mt-3">
          Couldn't generate — please try again in a moment.
        </p>
      )}
    </CollapsibleSection>
  );
```

`OutreachCard` is unchanged.

---

### Task 4: Refactor FormResponsePanel

**Files:**
- Modify: `frontend/src/components/jobs/FormResponsePanel.tsx`

- [ ] **Step 1: Add the import**

Find:

```tsx
import { useState } from 'react';
import { Check, ChevronDown, Copy, Loader2, Send, Trash2 } from 'lucide-react';
import {
  useAIOutputs,
  useDeleteAIOutput,
  useGenerateFormResponse,
} from '@/api/hooks';
import type { JobAIOutput } from '@/types/models';
```

Replace with:

```tsx
import { useState } from 'react';
import { Check, ChevronDown, Copy, Loader2, Send, Trash2 } from 'lucide-react';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';
import {
  useAIOutputs,
  useDeleteAIOutput,
  useGenerateFormResponse,
} from '@/api/hooks';
import type { JobAIOutput } from '@/types/models';
```

- [ ] **Step 2: Replace the outer wrapper and title row**

Replace the `return (` block in `FormResponsePanel(...)` (roughly lines 77–167) with:

```tsx
  const count = answers.length;
  const hint = list.isLoading
    ? 'Loading…'
    : count === 0
      ? 'Not yet generated'
      : `${count} version${count === 1 ? '' : 's'}`;

  return (
    <CollapsibleSection title="Form response" hint={hint}>
      <div className="space-y-3 mb-4">
        <div>
          <div className="mb-label mb-1">Application-form question</div>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Paste one question from the form — e.g. 'Describe a time you led a team through a difficult change.'"
            className="mb-input min-h-[110px] text-sm leading-relaxed"
            aria-label="Application form question"
          />
        </div>

        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <div className="mb-label mb-1">Word cap (optional)</div>
            <input
              type="number"
              min={20}
              max={1000}
              value={maxWords}
              onChange={(e) => setMaxWords(e.target.value)}
              placeholder="Claude picks"
              className="mb-input py-1 text-sm w-32"
              aria-label="Word cap"
            />
          </div>

          <div className="ml-auto">
            <button
              className="mb-btn-primary flex items-center gap-2"
              onClick={submit}
              disabled={!canGenerate}
            >
              {generate.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Send size={14} />
              )}
              {generate.isPending
                ? 'Drafting…'
                : answers.length === 0
                  ? 'Draft answer'
                  : 'Draft another'}
            </button>
          </div>
        </div>
      </div>

      {answers.length === 0 && !generate.isPending && (
        <p className="text-sm text-ink-3">
          Paste a single question from the application form and generate
          a tailored answer grounded in your profile and this job's
          description. Each draft is saved as its own version.
        </p>
      )}

      {answers.length > 0 && (
        <div className="space-y-3">
          {answers.map((a, i) => (
            <FormResponseCard
              key={a.id}
              output={a}
              defaultOpen={i === 0}
              onDelete={() => {
                if (confirm('Delete this answer? This cannot be undone.')) {
                  remove.mutate(a.id);
                }
              }}
            />
          ))}
        </div>
      )}

      {generate.isError && (
        <p className="text-sm text-rust mt-3">
          Couldn't generate — please try again in a moment.
        </p>
      )}
    </CollapsibleSection>
  );
```

`FormResponseCard`, `previewQuestion`, and `QUESTION_PREVIEW_MAX` stay unchanged.

---

### Task 5: Refactor FollowUpPanel

**Files:**
- Modify: `frontend/src/components/jobs/FollowUpPanel.tsx`

- [ ] **Step 1: Add the import**

Find:

```tsx
import { useState } from 'react';
import { Check, ChevronDown, Copy, Loader2, Send, Trash2 } from 'lucide-react';
import {
  useAIOutputs,
  useDeleteAIOutput,
  useGenerateFollowUp,
} from '@/api/hooks';
import type {
  FollowUpChannel,
  FollowUpStage,
  JobAIOutput,
} from '@/types/models';
```

Replace with:

```tsx
import { useState } from 'react';
import { Check, ChevronDown, Copy, Loader2, Send, Trash2 } from 'lucide-react';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';
import {
  useAIOutputs,
  useDeleteAIOutput,
  useGenerateFollowUp,
} from '@/api/hooks';
import type {
  FollowUpChannel,
  FollowUpStage,
  JobAIOutput,
} from '@/types/models';
```

- [ ] **Step 2: Replace the outer wrapper and title row**

Replace the `return (` block in `FollowUpPanel(...)` (roughly lines 65–179) with:

```tsx
  const count = messages.length;
  const hint = list.isLoading
    ? 'Loading…'
    : count === 0
      ? 'Not yet generated'
      : `${count} version${count === 1 ? '' : 's'}`;

  return (
    <CollapsibleSection title="Follow-up" hint={hint}>
      <div className="flex flex-wrap gap-4 mb-4">
        <div>
          <div className="mb-label mb-1">Stage</div>
          <div className="inline-flex rounded-full bg-parchment p-0.5 flex-wrap">
            {STAGES.map((s) => (
              <button
                key={s.value}
                onClick={() => setStage(s.value)}
                className={`px-3 py-1 text-xs rounded-full transition ${
                  stage === s.value ? 'bg-ink text-white' : 'text-ink-2'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="mb-label mb-1">Channel</div>
          <div className="inline-flex rounded-full bg-parchment p-0.5">
            {CHANNELS.map((c) => (
              <button
                key={c.value}
                onClick={() => setChannel(c.value)}
                className={`px-3 py-1 text-xs rounded-full transition ${
                  channel === c.value ? 'bg-ink text-white' : 'text-ink-2'
                }`}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>

        <div className="self-end ml-auto">
          <button
            className="mb-btn-primary flex items-center gap-2"
            onClick={submit}
            disabled={generate.isPending}
          >
            {generate.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
            {generate.isPending
              ? 'Drafting…'
              : messages.length === 0
                ? 'Draft follow-up'
                : 'Draft another'}
          </button>
        </div>
      </div>

      {/* Context is below the segmented row because it's optional and
          secondary — putting it beside the chips would visually compete
          with the stage choice, which is the more important knob. */}
      <div className="mb-4">
        <div className="mb-label mb-1">
          Specific callback (optional)
        </div>
        <textarea
          value={context}
          onChange={(e) => setContext(e.target.value)}
          placeholder="Anything specific to reference — e.g. 'the ownership model Sara described', 'the £65k ideal we discussed', 'thanks for the book recommendation'."
          className="mb-input min-h-[64px] text-sm leading-relaxed"
          aria-label="Specific callback"
          maxLength={500}
        />
      </div>

      {messages.length === 0 && !generate.isPending && (
        <p className="text-sm text-ink-3">
          Draft a follow-up tuned to where you are in the process — a
          post-interview thank-you reads nothing like a silent-period
          nudge. Each click saves a new version.
        </p>
      )}

      {messages.length > 0 && (
        <div className="space-y-3">
          {messages.map((m, i) => (
            <FollowUpCard
              key={m.id}
              output={m}
              defaultOpen={i === 0}
              onDelete={() => {
                if (confirm('Delete this follow-up? This cannot be undone.')) {
                  remove.mutate(m.id);
                }
              }}
            />
          ))}
        </div>
      )}

      {generate.isError && (
        <p className="text-sm text-rust mt-3">
          Couldn't generate — please try again in a moment.
        </p>
      )}
    </CollapsibleSection>
  );
```

`FollowUpCard` is unchanged.

---

### Task 6: Refactor InterviewPrepPanel

**Files:**
- Modify: `frontend/src/components/jobs/InterviewPrepPanel.tsx`

- [ ] **Step 1: Add the import**

Find:

```tsx
import { useState } from 'react';
import {
  BookOpen,
  Check,
  ChevronDown,
  Copy,
  Loader2,
  Trash2,
} from 'lucide-react';
import {
  useAIOutputs,
  useDeleteAIOutput,
  useGenerateInterviewPrep,
} from '@/api/hooks';
import type { InterviewPrepRound, JobAIOutput } from '@/types/models';
```

Replace with:

```tsx
import { useState } from 'react';
import {
  BookOpen,
  Check,
  ChevronDown,
  Copy,
  Loader2,
  Trash2,
} from 'lucide-react';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';
import {
  useAIOutputs,
  useDeleteAIOutput,
  useGenerateInterviewPrep,
} from '@/api/hooks';
import type { InterviewPrepRound, JobAIOutput } from '@/types/models';
```

- [ ] **Step 2: Replace the outer wrapper and title row**

Replace the `return (` block in `InterviewPrepPanel(...)` (roughly lines 63–162) with:

```tsx
  const count = sheets.length;
  const hint = list.isLoading
    ? 'Loading…'
    : count === 0
      ? 'Not yet generated'
      : `${count} version${count === 1 ? '' : 's'}`;

  return (
    <CollapsibleSection title="Interview prep" hint={hint}>
      <div className="flex flex-wrap gap-4 mb-3">
        <div>
          <div className="mb-label mb-1">Round</div>
          <div className="inline-flex rounded-full bg-parchment p-0.5 flex-wrap">
            {ROUNDS.map((r) => (
              <button
                key={r.value}
                onClick={() => setRound(r.value)}
                className={`px-3 py-1 text-xs rounded-full transition ${
                  round === r.value ? 'bg-ink text-white' : 'text-ink-2'
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div className="self-end ml-auto">
          <button
            className="mb-btn-primary flex items-center gap-2"
            onClick={submit}
            disabled={generate.isPending}
          >
            {generate.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <BookOpen size={14} />
            )}
            {generate.isPending
              ? 'Preparing…'
              : sheets.length === 0
                ? 'Generate prep sheet'
                : 'Generate another'}
          </button>
        </div>
      </div>

      {/* Focus sits below because it's optional and narrower in effect
          than the round selector — it biases question selection, it
          doesn't redefine the sheet. */}
      <div className="mb-4">
        <div className="mb-label mb-1">Focus (optional)</div>
        <input
          type="text"
          value={focus}
          onChange={(e) => setFocus(e.target.value)}
          placeholder="e.g. system design, React hooks, team leadership"
          className="mb-input py-1 text-sm"
          aria-label="Topic focus"
          maxLength={200}
        />
      </div>

      {sheets.length === 0 && !generate.isPending && (
        <p className="text-sm text-ink-3">
          Generate a prep sheet tailored to the upcoming round and this
          role — likely technical and behavioural questions, plus
          thoughtful questions for you to ask the interviewer. Each
          click saves a new version.
        </p>
      )}

      {sheets.length > 0 && (
        <div className="space-y-3">
          {sheets.map((s, i) => (
            <PrepCard
              key={s.id}
              output={s}
              defaultOpen={i === 0}
              onDelete={() => {
                if (
                  confirm('Delete this prep sheet? This cannot be undone.')
                ) {
                  remove.mutate(s.id);
                }
              }}
            />
          ))}
        </div>
      )}

      {generate.isError && (
        <p className="text-sm text-rust mt-3">
          Couldn't generate — please try again in a moment.
        </p>
      )}
    </CollapsibleSection>
  );
```

`PrepCard` is unchanged.

---

### Task 7: Refactor CompanyResearchPanel (with relTime export)

**Files:**
- Modify: `frontend/src/components/jobs/CompanyResearchPanel.tsx`

This panel is structurally different from the other five:
1. It has an early `if (query.isLoading) return ...` that needs to be folded into the main render so `CollapsibleSection` can always provide the wrapper.
2. Its existing `CacheStatus` component lives inside the header row — after the refactor, the wrapper's `hint` prop renders the equivalent label.
3. `relTime` is defined locally at the bottom of the file; it must be exported so the header-hint logic can use it.

- [ ] **Step 1: Add the import**

Find:

```tsx
import { useState } from 'react';
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Copy,
  ExternalLink,
  Globe,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { ApiError } from '@/api/client';
import {
  useCompanyResearch,
  useGenerateCompanyResearch,
} from '@/api/hooks';
import type { CompanyResearch } from '@/types/models';
```

Replace with:

```tsx
import { useState } from 'react';
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Copy,
  ExternalLink,
  Globe,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { ApiError } from '@/api/client';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';
import {
  useCompanyResearch,
  useGenerateCompanyResearch,
} from '@/api/hooks';
import type { CompanyResearch } from '@/types/models';
```

- [ ] **Step 2: Export `relTime`**

Find the `relTime` declaration near the bottom of the file:

```tsx
function relTime(ms: number): string {
```

Change to:

```tsx
export function relTime(ms: number): string {
```

(One-word edit. The implementation body stays identical.)

- [ ] **Step 3: Replace the whole CompanyResearchPanel return block**

Replace the full function body of `CompanyResearchPanel` — from `export function CompanyResearchPanel(...)` down to its closing `}` (roughly lines 37–141) — with:

```tsx
export function CompanyResearchPanel({
  jobId,
  companyName,
}: {
  jobId: string;
  companyName: string;
}) {
  const query = useCompanyResearch(jobId);
  const generate = useGenerateCompanyResearch(jobId);

  const status404 =
    query.isError && query.error instanceof ApiError && query.error.status === 404;
  const status400 =
    query.isError && query.error instanceof ApiError && query.error.status === 400;
  const otherError =
    query.isError && !status404 && !status400 ? query.error : null;

  // Header hint mirrors the states the expanded body renders so the
  // collapsed row tells the user what's inside without opening it.
  // `· stale` matches CacheStatus's expanded label for parity.
  let hint: string | null = null;
  if (query.isLoading) {
    hint = 'Loading…';
  } else if (status400) {
    hint = 'No company set';
  } else if (status404) {
    hint = 'Not yet researched';
  } else if (otherError) {
    hint = 'Error';
  } else if (query.data?.fresh) {
    hint = 'Just researched';
  } else if (query.data) {
    const ageMs = Date.now() - Date.parse(query.data.cached_at);
    const stale = Date.parse(query.data.expires_at) < Date.now();
    hint = `Cached ${relTime(ageMs)} ago${stale ? ' · stale' : ''}`;
  }

  return (
    <CollapsibleSection title="Company research" hint={hint}>
      {query.isLoading && (
        <p className="text-sm text-ink-3">Loading…</p>
      )}

      {status400 && (
        <div className="flex items-start gap-2 text-sm text-ink-2">
          <AlertTriangle size={16} className="text-gold shrink-0 mt-0.5" />
          <p>
            This job doesn't have a company name yet, so there's nothing
            for us to research. Edit the job details above to add one
            and then try again.
          </p>
        </div>
      )}

      {status404 && !generate.isPending && (
        <div>
          <p className="text-sm text-ink-3 mb-3">
            Pull in public context on{' '}
            <span className="font-medium text-ink-2">{companyName}</span>{' '}
            — recent news, culture signals, interview process, and a few
            sharp questions to probe. Uses web search; takes ~30 seconds.
          </p>
          <button
            className="mb-btn-primary flex items-center gap-2"
            onClick={() => generate.mutate()}
            disabled={generate.isPending}
          >
            <Globe size={14} />
            Research company
          </button>
        </div>
      )}

      {generate.isPending && (
        <div className="flex items-start gap-2 text-sm text-ink-2">
          <Loader2 size={16} className="animate-spin shrink-0 mt-0.5" />
          <div>
            <p className="font-medium">Researching {companyName}…</p>
            <p className="text-xs text-ink-3 mt-1">
              Claude is running up to 5 web searches and synthesising
              the results. This usually takes 15–30 seconds.
            </p>
          </div>
        </div>
      )}

      {otherError && !generate.isPending && (
        <p className="text-sm text-rust">
          Couldn't load research: {otherError.message}
        </p>
      )}

      {query.data && !generate.isPending && (
        <BriefingView
          data={query.data}
          onRefresh={() => generate.mutate()}
          refreshing={generate.isPending}
        />
      )}

      {generate.isError && (
        <p className="text-sm text-rust mt-3">
          {generate.error instanceof ApiError && generate.error.message
            ? generate.error.message
            : 'Research failed — please try again in a moment.'}
        </p>
      )}
    </CollapsibleSection>
  );
}
```

Key differences from the current code:
- The early `if (query.isLoading) return (<div className="mb-card">...</div>)` block is gone; the loading state is rendered inside the CollapsibleSection as `{query.isLoading && <p>Loading…</p>}`.
- The old header row (`<div className="flex items-center justify-between mb-3 flex-wrap gap-2">`) and its inline `<CacheStatus />` are removed — the wrapper's `hint` prop renders the equivalent summary.
- `CacheStatus` is no longer referenced anywhere in the file. Leave the component definition in place for now; a follow-up can delete it if unused. (Dead code is cheap; removing now widens the diff.)
- `BriefingView` continues to render inside the expanded body exactly as before; it still handles its own per-briefing show/hide toggle.

- [ ] **Step 4: Confirm `CacheStatus` is unreferenced**

Run:

```bash
grep -n "CacheStatus" /Users/thomashughes/Desktop/Projects/matchbookv2/frontend/src/components/jobs/CompanyResearchPanel.tsx
```

Expected: only the `function CacheStatus(` declaration line matches — zero call sites. (Unused, but left in place.)

---

### Task 8: Rebuild frontend and verify end-to-end in the browser

**Files:** none (build + smoke test)

- [ ] **Step 1: Rebuild the frontend image**

```bash
docker compose up -d --build frontend
```

Expected: build completes without errors, frontend container transitions to `Up`.

- [ ] **Step 2: Check for TypeScript errors in the build log**

```bash
docker compose logs --tail=120 frontend
```

Expected: no lines containing `error TS`, `Module not found`, or `Failed to resolve`. If any appear, fix and rebuild before proceeding.

- [ ] **Step 3: Confirm frontend serves**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3085/
```

Expected: `200`.

- [ ] **Step 4: Manual browser verification**

Open `http://localhost:3085/jobs/<any job id>` and verify each of the following on a job with at least one cover letter and zero outreach versions:

1. All six AI panels render below the Status card, **all collapsed by default**.
2. Each header shows `Title ▸ hint`, specifically:
   - Cover letter: `1 version` (or `N versions`)
   - Outreach: `Not yet generated`
   - Form response: `Not yet generated`
   - Follow-up: `Not yet generated`
   - Interview prep: `Not yet generated`
   - Company research: `Not yet researched` (404 from the GET is expected)
3. The Notes card and raw JD disclosure below are **unchanged**.
4. Click the "Cover letter" header → expands to the full panel (tone/length controls, version cards with inner per-version collapse, Generate button).
5. Click again → collapses.
6. Keyboard: Tab to any collapsed header → browser focus ring visible. Press Space → toggles open. Press Space again → toggles closed.
7. Reload the page → all panels collapsed again (no persistence, expected).
8. Navigate to a different job → panels collapsed for that job too (fresh state per mount).
9. Scroll-to-bottom test: with all six panels collapsed, the page is noticeably shorter than it was before (the whole point).

- [ ] **Step 5: Report back**

Summarise for the user:
- All eight tasks complete.
- Manual verification pass/fail per step above.
- Any unexpected visual gaps or regressions.

Do **not** commit — the user tests first and commits later.

---

## Self-review (done at plan-write time)

- **Spec coverage:**
  - "Collapse all six AI panels by default" → Tasks 2–7 each wrap in `defaultOpen=false` (the default).
  - "Each collapsed header shows a content-state hint" → hint computed in every panel task.
  - "Notes and raw JD unchanged" → no task touches `JobDetailPage.tsx`.
  - "Same card chrome + header pattern across all six" → Task 1 owns it.
  - "relTime lifted from CompanyResearchPanel, same file" → Task 7 Step 2.
  - "`stale` suffix parity with CacheStatus" → Task 7 Step 3 hint logic.
  - Accessibility (`aria-expanded`, Enter/Space) → Task 1 component + Task 8 Step 4 (6).
- **Placeholder scan:** no TBD / TODO. All steps include exact file paths, exact code, exact commands.
- **Type consistency:** `CollapsibleSection` prop names (`title`, `hint`, `defaultOpen`, `children`) are identical across Task 1 and every consumer in Tasks 2–7. `relTime` signature (`(ms: number) => string`) matches both its definition and its single consumer.
- **Scope:** single feature, single implementation pass. Front-end only.

No issues found.
