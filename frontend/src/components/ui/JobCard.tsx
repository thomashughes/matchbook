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
        <div className="mt-1 flex items-center gap-4 text-sm text-ink-2">
          <span className="inline-flex items-center gap-1">
            <Briefcase size={14} className="text-ink-3" />
            {job.company}
          </span>
          {job.location && (
            <span className="inline-flex items-center gap-1">
              <MapPin size={14} className="text-ink-3" />
              {job.location}
            </span>
          )}
          {job.salary_raw && (
            <span className="text-ink-3">{job.salary_raw}</span>
          )}
        </div>
      </div>
    </Link>
  );
}
