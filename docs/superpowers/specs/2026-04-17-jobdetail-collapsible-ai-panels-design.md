# JobDetailPage — collapsible AI panels (sub-project A)

**Date:** 2026-04-17
**Status:** Design approved, spec awaiting user review.
**Scope:** Frontend only. No backend, no schema, no API changes.

## Context

`JobDetailPage.tsx` currently renders six AI action panels below the
Status card, each as a full `mb-card`. Once a user has generated several
cover letter versions, outreach drafts, follow-ups, etc., the page
becomes a long vertical scroll and the user cannot see at a glance which
sections are populated vs empty. The Notes card and raw JD disclosure
already have their own UX affordances and are working fine.

## Goals

- Collapse all six AI panels by default on page load so the view fits
  on one screen for the common "I just want to see the score + status"
  interaction.
- Make it obvious from the collapsed state which panels have content
  and which are empty, without forcing the user to open each one.
- Keep the fully-expanded experience identical to today — no feature
  regressions inside any panel.
- Zero backend changes. Zero new dependencies.

## Non-goals

- Persisting open/closed state across reloads or across devices.
- Auto-opening panels based on recent activity.
- Changing the order, styling, or behaviour of the Notes card or
  the existing "Show / Hide full job description" disclosure.
- Touching the Cover letter / Outreach / etc. panel internals beyond
  stripping their outer `mb-card` wrapper.

## User-facing behaviour

- On every visit to `/jobs/:id`, all six AI panels start collapsed.
- Each collapsed header shows: a chevron, the section title, and a
  right-aligned one-line hint describing content state.
- Clicking anywhere on the header row (or pressing Enter/Space while
  focused) toggles the panel open/closed. Chevron rotates 90° to
  indicate state.
- Expanded panels look and behave exactly as today.
- Notes and raw JD sections are untouched.

### Per-panel hint text

| Panel            | Populated                              | Empty                  | Loading      |
| ---------------- | -------------------------------------- | ---------------------- | ------------ |
| Cover letter     | `N version` / `N versions`             | `Not yet generated`    | `Loading…`   |
| Outreach         | `N version` / `N versions`             | `Not yet generated`    | `Loading…`   |
| Form response    | `N version` / `N versions`             | `Not yet generated`    | `Loading…`   |
| Follow-up        | `N version` / `N versions`             | `Not yet generated`    | `Loading…`   |
| Interview prep   | `N version` / `N versions`             | `Not yet generated`    | `Loading…`   |
| Company research | `Just researched` \| `Cached {Nd} ago` | `Not yet researched`   | `Loading…`   |

Company research uses the same `relTime` formatter the panel already
uses internally (`Nm` / `Nh` / `Nd` buckets).

## Design

### New component

`frontend/src/components/ui/CollapsibleSection.tsx`

```tsx
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

Uses only existing tokens (`mb-card`, `mb-display`, `text-ink-3`).
No animation on the body reveal — acceptable because the chevron
rotation already communicates the state change and a height-animation
for variable-content panels is a significant complexity tax for little
gain.

The component stores open state in local React state only. There is no
persistence layer and no `id`-based key; re-mounting the component
(e.g. navigating between jobs) resets state, which is the desired
behaviour per the Non-goals.

### Per-panel integration pattern

Each of the six panels is refactored to:

1. Drop its own outer `<div className="mb-card">` wrapper — the
   `CollapsibleSection` provides that chrome now.
2. Wrap its top-level return in `<CollapsibleSection title={…} hint={…}>`.
3. Compute a `hint` string from its existing query data — no new hooks,
   no lifted state.

For the five version-based panels (Cover letter, Outreach, Form
response, Follow-up, Interview prep) the hint is derived from the
same list the panel already consumes:

```ts
const count = list.data?.length ?? 0;
const hint = list.isLoading
  ? 'Loading…'
  : count === 0
    ? 'Not yet generated'
    : `${count} version${count === 1 ? '' : 's'}`;
```

For Company research the hint uses `query.data` from
`useCompanyResearch(jobId)` and mirrors the same `stale` logic the
existing `CacheStatus` component already applies inside the panel, so
the header label stays in sync with what the user sees once expanded:

```ts
let hint: string | null = null;
if (query.isLoading) {
  hint = 'Loading…';
} else if (status404) {
  hint = 'Not yet researched';
} else if (query.data?.fresh) {
  hint = 'Just researched';
} else if (query.data) {
  const ageMs = Date.now() - Date.parse(query.data.cached_at);
  const stale = Date.parse(query.data.expires_at) < Date.now();
  hint = `Cached ${relTime(ageMs)} ago${stale ? ' · stale' : ''}`;
}
```

The existing `relTime` helper lives inside `CompanyResearchPanel.tsx`
— export it (named export, same file) so the header-hint computation
can import it without duplicating the minute/hour/day bucketing. If a
third consumer ever appears, promote it to `lib/time.ts` then.

### Accessibility

- The header is a native `<button type="button">` so it is reachable
  by Tab, activated by Enter or Space, and announces its expanded
  state via `aria-expanded`.
- The Generate / Copy / Delete buttons inside the panel body are NOT
  nested inside the header button. They sit in the `{open && ...}`
  branch, as siblings of the header.
- The chevron visually rotates but is not announced — the
  `aria-expanded` on the header button is the authoritative signal.

### JobDetailPage layout

No structural changes. The six panels continue to render in the same
order (`CoverLetterPanel`, `OutreachPanel`, `FormResponsePanel`,
`FollowUpPanel`, `InterviewPrepPanel`, `CompanyResearchPanel`) between
the Status card and the Notes card at lines 181–191. Each panel is
now self-wrapping in `CollapsibleSection`, so `JobDetailPage.tsx`
itself doesn't change at all.

## Verification

Manual browser test against a job with mixed state:

1. Open a job that has at least one Cover letter and zero Outreach
   versions.
2. Expect the page to show all six AI panels collapsed, Status +
   Notes + raw JD disclosure unchanged.
3. Expect `Cover letter · 1 version` and `Outreach · Not yet
   generated` in the right of their respective headers.
4. Click the Cover letter header → expands to current panel UI
   (segmented controls, version cards, Generate button).
5. Click again → collapses.
6. Reload → all six collapsed again.
7. Keyboard: Tab to a header, press Space → expands. Tab into the
   body, confirm Generate / Copy / Delete work.
8. Generate a new outreach (once API quota resets) → count updates to
   `1 version` while expanded; collapse → still shows `1 version`.

No automated tests for this change — the codebase has no frontend
test harness at present, and introducing one is out of scope.

## Rollout

One PR, one rebuild (`docker compose up -d --build frontend`). No
migration, no data change, no env var. Backwards-compatible with any
in-flight panel state because there isn't any persisted.

## Open questions

None at spec-review time.
