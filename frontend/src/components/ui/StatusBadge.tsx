/**
 * StatusBadge — pill for the job application status.
 *
 * Each status gets its own distinct colour so moving a job through the
 * pipeline feels like visible progress rather than shades of the same
 * accent. Neutral → warm → cool → strong-positive / negative:
 *
 *   saved        — parchment / ink-3 (neutral, "not yet acted on")
 *   applied      — gold               (warm, active)
 *   interviewing — blue               (cool, mid-pipeline)
 *   offer        — teal               (strong positive outcome)
 *   rejected     — rust               (negative terminal state)
 *
 * Blue for interviewing is an addition outside the default palette —
 * we need a fifth distinct hue and a muted blue sits naturally next to
 * the warm accents without stealing attention from teal (offer).
 */
import type { JobStatus } from '@/types/models';

const COLOURS: Record<JobStatus, { bg: string; fg: string; label: string }> = {
  saved:        { bg: 'bg-parchment',   fg: 'text-ink-2',        label: 'Saved' },
  applied:      { bg: 'bg-gold-light',  fg: 'text-gold',         label: 'Applied' },
  interviewing: { bg: 'bg-[#dbe7f3]',   fg: 'text-[#2b5d89]',    label: 'Interviewing' },
  offer:        { bg: 'bg-teal-light',  fg: 'text-teal',         label: 'Offer' },
  rejected:     { bg: 'bg-rust-light',  fg: 'text-rust',         label: 'Rejected' },
};

export function StatusBadge({ status }: { status: JobStatus }) {
  const c = COLOURS[status];
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${c.bg} ${c.fg}`}>
      {c.label}
    </span>
  );
}
