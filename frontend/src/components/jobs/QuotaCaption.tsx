/**
 * Small caption that sits under a generate button telling the user
 * how many drafts of this kind they have left this month, on this
 * specific job.
 *
 * Reads from the JobDetail cache — no extra fetch. The JobDetailPage
 * already queries useJob(id) on mount, so this component is a pure
 * subscriber to that cached data.
 *
 * Three visual states:
 *   - remaining > 0 & > 20%: muted caption "2 of 3 drafts left this month"
 *   - remaining > 0 & <= 20%: rust-coloured caption (getting close)
 *   - remaining === 0       : rust "Upgrade to continue" link to /billing
 *   - unlimited (grandfathered): subtle "Unlimited" text
 *
 * If no matching quota row exists (rare — means the create_job response
 * was cached before quota was populated, or data isn't loaded yet), the
 * component renders nothing. A missing caption is better than a wrong one.
 */
import { Link } from 'react-router-dom';
import { useJob } from '@/api/hooks';
import type { EntitlementResource } from '@/types/models';

const LABELS: Partial<Record<EntitlementResource, string>> = {
  draft_outreach: 'outreach draft',
  draft_form_response: 'response draft',
  draft_follow_up: 'follow-up draft',
  draft_interview_prep: 'interview-prep sheet',
  cover_letter: 'cover letter',
};

export function QuotaCaption({
  jobId,
  resource,
}: {
  jobId: string;
  resource: EntitlementResource;
}) {
  const { data } = useJob(jobId);
  const item = data?.quota.find((q) => q.resource === resource);
  if (!item) return null;

  const label = LABELS[resource] ?? 'draft';

  // Unlimited = grandfathered. No nagging, just acknowledge it exists.
  if (item.limit === null || item.remaining === null) {
    return <div className="text-xs text-ink-3 mt-2">Unlimited ({label}s)</div>;
  }

  if (item.remaining === 0) {
    return (
      <div className="text-xs mt-2" style={{ color: 'var(--rust, #b0552d)' }}>
        No {label}s left this month —{' '}
        <Link to="/billing" className="underline font-medium">
          upgrade to continue
        </Link>
        .
      </div>
    );
  }

  const low = item.limit > 0 && item.remaining / item.limit <= 0.34;
  return (
    <div
      className="text-xs mt-2"
      style={{ color: low ? 'var(--rust, #b0552d)' : 'var(--ink-3, #7f7668)' }}
    >
      {item.remaining} of {item.limit} {label}
      {item.remaining === 1 ? '' : 's'} left this month
    </div>
  );
}
