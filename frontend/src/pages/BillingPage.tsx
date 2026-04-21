/**
 * /billing — shows the user's current plan, a usage table, and one of
 * two CTAs:
 *   - Free user → "Upgrade to Paid" (opens Stripe Checkout)
 *   - Paid/cancelling user → "Manage subscription" (opens Stripe Portal)
 *   - Grandfathered user → flat "You have unlimited access" message
 *
 * Design note: nothing on this page talks to Stripe directly. The
 * backend creates the Checkout/Portal session and returns a URL; we
 * redirect the browser. All PCI-sensitive UX happens in Stripe's own
 * hosted pages.
 */
import { useSearchParams } from 'react-router-dom';
import { useBillingStatus, useCreateCheckout, useOpenBillingPortal } from '@/api/hooks';
import type { QuotaItem } from '@/types/models';

const RESOURCE_LABELS: Record<string, string> = {
  jobs_created: 'Jobs added',
  company_research: 'Company research',
  draft_outreach: 'Outreach drafts',
  draft_form_response: 'Form responses',
  draft_follow_up: 'Follow-up drafts',
  draft_interview_prep: 'Interview prep sheets',
  cover_letter: 'Cover letters',
  ai_job_search: 'AI job searches',
  cv_generation: 'CV generations',
};

function formatResetDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

function UsageRow({ item }: { item: QuotaItem }) {
  const label = RESOURCE_LABELS[item.resource] ?? item.resource;
  const unlimited = item.limit === null;
  const ratio =
    !unlimited && item.limit! > 0 ? Math.min(item.used / item.limit!, 1) : 0;
  const hot = ratio >= 0.8;

  return (
    <div
      className="flex items-center justify-between py-3"
      style={{ borderBottom: '0.5px solid var(--border)' }}
    >
      <div>
        <div className="text-sm font-medium text-ink">{label}</div>
        <div className="text-xs text-ink-muted mt-0.5">
          Resets {formatResetDate(item.resets_at)}
        </div>
      </div>
      <div className="text-right">
        {unlimited ? (
          <span className="text-sm font-medium" style={{ color: 'var(--gold, #b8943d)' }}>
            Unlimited
          </span>
        ) : (
          <>
            <div
              className="text-sm font-medium"
              style={{ color: hot ? 'var(--rust, #b0552d)' : 'var(--ink)' }}
            >
              {item.used} / {item.limit}
            </div>
            <div
              className="h-1 w-24 rounded-full mt-1"
              style={{ background: 'var(--parchment)' }}
            >
              <div
                className="h-1 rounded-full transition-all"
                style={{
                  width: `${ratio * 100}%`,
                  background: hot ? 'var(--rust, #b0552d)' : 'var(--teal, #1f8a8a)',
                }}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export function BillingPage() {
  const [params] = useSearchParams();
  const checkoutStatus = params.get('status'); // 'success' | 'cancel' | null
  const { data, isLoading } = useBillingStatus();
  const checkout = useCreateCheckout();
  const portal = useOpenBillingPortal();

  if (isLoading || !data) {
    return (
      <div className="max-w-3xl mx-auto px-7 py-8">
        <h1 className="text-2xl font-semibold text-ink mb-6">Billing</h1>
        <div className="text-ink-muted">Loading…</div>
      </div>
    );
  }

  const planLabel =
    data.plan === 'paid'
      ? 'Paid — £7.99/month'
      : data.plan === 'paid_grandfathered'
        ? 'Unlimited (grandfathered)'
        : 'Free';

  return (
    <div className="max-w-3xl mx-auto px-7 py-8">
      <h1 className="text-2xl font-semibold text-ink mb-6">Billing</h1>

      {/* Post-checkout banner — shown only right after the Stripe
          redirect. Doesn't persist; reloading the page clears it. */}
      {checkoutStatus === 'success' && (
        <div
          className="mb-6 px-4 py-3 rounded-lg text-sm"
          style={{
            background: 'var(--teal-soft, #d9ecec)',
            color: 'var(--teal, #1f8a8a)',
          }}
        >
          Thanks! If your payment went through, your plan will update within a
          few seconds — refresh this page if it doesn't show yet.
        </div>
      )}
      {checkoutStatus === 'cancel' && (
        <div
          className="mb-6 px-4 py-3 rounded-lg text-sm"
          style={{ background: 'var(--parchment)', color: 'var(--ink-muted)' }}
        >
          Checkout cancelled — you're still on the free plan.
        </div>
      )}

      {/* Plan card */}
      <div
        className="rounded-xl px-6 py-5 mb-8"
        style={{ background: 'var(--card)', border: '0.5px solid var(--border)' }}
      >
        <div className="text-xs uppercase tracking-wide text-ink-muted">
          Current plan
        </div>
        <div className="text-lg font-semibold text-ink mt-1">{planLabel}</div>

        {/* Pending cancellation notice — appears when the user has
            scheduled cancellation but the period hasn't ended yet. */}
        {data.cancel_at_period_end && data.current_period_end && (
          <div className="text-xs mt-2" style={{ color: 'var(--rust, #b0552d)' }}>
            Your subscription ends {formatResetDate(data.current_period_end)}. After
            that you'll drop to the free plan.
          </div>
        )}

        <div className="mt-4">
          {data.plan === 'free' && (
            <button
              className="mb-btn-primary"
              onClick={() => checkout.mutate()}
              disabled={checkout.isPending}
            >
              {checkout.isPending ? 'Opening Stripe…' : 'Upgrade to Paid'}
            </button>
          )}
          {data.plan === 'paid' && (
            <button
              className="mb-btn-secondary"
              onClick={() => portal.mutate()}
              disabled={portal.isPending}
            >
              {portal.isPending ? 'Opening Stripe…' : 'Manage subscription'}
            </button>
          )}
          {data.plan === 'paid_grandfathered' && (
            <div className="text-xs text-ink-muted">
              You have unlimited access as a grandfathered account. No billing
              action is needed.
            </div>
          )}
        </div>

        {(checkout.isError || portal.isError) && (
          <div
            className="text-xs mt-3"
            style={{ color: 'var(--rust, #b0552d)' }}
          >
            Something went wrong reaching Stripe. Try again in a moment.
          </div>
        )}
      </div>

      {/* Usage */}
      <h2 className="text-sm font-semibold text-ink uppercase tracking-wide mb-2">
        This month's usage
      </h2>
      <div
        className="rounded-xl px-6"
        style={{ background: 'var(--card)', border: '0.5px solid var(--border)' }}
      >
        {data.usage.map((item) => (
          <UsageRow key={item.resource} item={item} />
        ))}
      </div>

      {/* Per-job usage footnote — users asking "where are my drafts?"
          need the pointer. */}
      <p className="text-xs text-ink-muted mt-4">
        Draft limits (cover letters, outreach, follow-ups, interview prep,
        form responses) are tracked separately for each job. You'll see the
        remaining count on the generate buttons inside a job.
      </p>
    </div>
  );
}
