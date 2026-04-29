/**
 * StatusBadge — pill for the job application status.
 *
 * Each stage gets a distinct hue so moving a job through the pipeline
 * feels like visible progress. The three interview rounds share the
 * same blue family and deepen as you advance — the user reads "darker
 * blue = further along" without needing to parse the label. Terminal
 * states (rejected/withdrawn/declined/ghosted) use warm-grey/rust
 * variants so they don't compete with the in-flight stages for
 * attention.
 */
import type { JobStatus } from '@/types/models';

const COLOURS: Record<JobStatus, { bg: string; fg: string; label: string }> = {
  saved:            { bg: 'bg-parchment',   fg: 'text-ink-2',     label: 'Saved' },
  applied:          { bg: 'bg-gold-light',  fg: 'text-gold',      label: 'Applied' },
  first_interview:  { bg: 'bg-[#dbe7f3]',   fg: 'text-[#2b5d89]', label: 'First interview' },
  second_interview: { bg: 'bg-[#c4d6ea]',   fg: 'text-[#1f4670]', label: 'Second interview' },
  final_interview:  { bg: 'bg-[#a8c2dd]',   fg: 'text-[#13355a]', label: 'Final interview' },
  offer:            { bg: 'bg-teal-light',  fg: 'text-teal',      label: 'Offer' },
  accepted:         { bg: 'bg-teal',        fg: 'text-cream',     label: 'Accepted' },
  rejected:         { bg: 'bg-rust-light',  fg: 'text-rust',      label: 'Rejected' },
  withdrawn:        { bg: 'bg-ink-4',       fg: 'text-ink-1',     label: 'Withdrawn' },
  declined:         { bg: 'bg-ink-4',       fg: 'text-ink-1',     label: 'Declined' },
  ghosted:          { bg: 'bg-ink-4',       fg: 'text-ink-2',     label: 'Ghosted' },
};

export function StatusBadge({ status }: { status: JobStatus }) {
  const c = COLOURS[status];
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${c.bg} ${c.fg}`}>
      {c.label}
    </span>
  );
}
