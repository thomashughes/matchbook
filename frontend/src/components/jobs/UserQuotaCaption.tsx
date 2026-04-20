/**
 * Same visual contract as QuotaCaption but reads from /billing/status
 * instead of JobDetail.quota. Used for per-user resources (company
 * research, in practice — jobs_created shows in the top-bar pill and
 * doesn't need an inline caption).
 *
 * Separate file + component to keep the per-job vs per-user data
 * sources obvious at the call site. Callers write:
 *   <QuotaCaption jobId={...} resource="draft_*" />          // per-job
 *   <UserQuotaCaption resource="company_research" />         // per-user
 * and never mix them up.
 */
import { Link } from 'react-router-dom';
import { useBillingStatus } from '@/api/hooks';
import type { EntitlementResource } from '@/types/models';

const LABELS: Partial<Record<EntitlementResource, string>> = {
  company_research: 'research',
  jobs_created: 'job',
  ai_job_search: 'AI job search',
};

export function UserQuotaCaption({
  resource,
}: {
  resource: EntitlementResource;
}) {
  const { data } = useBillingStatus();
  const item = data?.usage.find((u) => u.resource === resource);
  if (!item) return null;

  const label = LABELS[resource] ?? 'credit';

  if (item.limit === null || item.remaining === null) {
    return <div className="text-xs text-ink-3 mt-2">Unlimited</div>;
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
