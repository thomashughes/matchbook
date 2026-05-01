/**
 * JobCard — used in dashboard recent-jobs and the full job list.
 *
 * Score is the visual hero per §7.4 ("Score as hero"): placed leading
 * on the card at a generous size. The rest of the card supports it —
 * title, company, location, status — rather than competing.
 */
import { Link } from 'react-router-dom';
import { MapPin, Briefcase } from 'lucide-react';
import { ScoreRing } from './ScoreRing';
import { StatusBadge } from './StatusBadge';
import type { JobListItem } from '@/types/models';

export function JobCard({ job }: { job: JobListItem }) {
  return (
    <Link
      to={`/jobs/${job.id}`}
      className="mb-card flex items-center gap-4 hover:shadow-sm transition"
    >
      <ScoreRing score={job.total_score} size={56} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="mb-display text-lg text-ink truncate">{job.title}</div>
          <StatusBadge status={job.status} />
        </div>
        {/* flex-wrap + min-w-0 on the inline-flex chunks lets the row
            collapse cleanly on narrow cards: company truncates first,
            then location / salary wrap to a second line rather than
            blowing past the card edge. */}
        <div className="mt-1 flex items-center flex-wrap gap-x-4 gap-y-1 text-sm text-ink-2">
          <span className="inline-flex items-center gap-1 min-w-0 max-w-full">
            <Briefcase size={14} className="text-ink-3 shrink-0" />
            <span className="truncate">{job.company}</span>
          </span>
          {job.location && (
            <span className="inline-flex items-center gap-1 min-w-0 max-w-full">
              <MapPin size={14} className="text-ink-3 shrink-0" />
              <span className="truncate">{job.location}</span>
            </span>
          )}
          {job.salary_raw && (
            <span className="text-ink-3 whitespace-nowrap">{job.salary_raw}</span>
          )}
        </div>
      </div>
    </Link>
  );
}
