/**
 * Small top-bar widget that shows the user's two most-watched caps:
 * jobs and company research. Clicking it opens /billing.
 *
 * Visual rules (Warm Modern palette via mb- tokens):
 *   - < 80% of either cap used: neutral ink-on-parchment.
 *   - ≥ 80%                     : rust-coloured accent — the user is
 *     close to hitting the wall and should see the upgrade CTA.
 *   - grandfathered / unlimited : renders "Unlimited" pill in muted gold.
 *
 * Placement: rendered in TopBar to the left of the "Add job" button.
 */
import { Link } from 'react-router-dom';
import { useBillingStatus } from '@/api/hooks';

const THRESHOLD = 0.8;

function ratio(used: number, limit: number | null): number {
  if (limit === null || limit === 0) return 0;
  return used / limit;
}

export function UsagePill() {
  const { data, isLoading } = useBillingStatus();

  if (isLoading || !data) {
    // Avoid a layout jump — reserve the space with an invisible
    // placeholder the same width as the real pill.
    return <div className="w-[180px] h-8" />;
  }

  const jobs = data.usage.find((u) => u.resource === 'jobs_created');
  const research = data.usage.find((u) => u.resource === 'company_research');

  // Grandfathered users see a flat "Unlimited" badge. Hide the numeric
  // noise — there's nothing to watch.
  if (data.plan === 'paid_grandfathered') {
    return (
      <Link
        to="/billing"
        className="text-xs font-medium px-3 py-1.5 rounded-full"
        style={{ background: 'var(--gold-soft, #f3e6c2)', color: 'var(--ink)' }}
        title="Grandfathered account — unlimited usage"
      >
        Unlimited
      </Link>
    );
  }

  const jobsRatio = jobs ? ratio(jobs.used, jobs.limit) : 0;
  const researchRatio = research ? ratio(research.used, research.limit) : 0;
  const hot = jobsRatio >= THRESHOLD || researchRatio >= THRESHOLD;

  return (
    <Link
      to="/billing"
      className="text-xs font-medium px-3 py-1.5 rounded-full inline-flex items-center gap-3 transition-colors"
      style={{
        background: hot ? 'var(--rust-soft, #f5dcc8)' : 'var(--parchment)',
        color: hot ? 'var(--rust, #b0552d)' : 'var(--ink)',
      }}
      title={`Plan: ${data.plan === 'paid' ? 'Paid' : 'Free'}. Click to manage billing.`}
    >
      {jobs && (
        <span>
          {jobs.used}/{jobs.limit} jobs
        </span>
      )}
      {research && (
        <span>
          {research.used}/{research.limit} research
        </span>
      )}
    </Link>
  );
}
