/**
 * CompanyResearchPanel — Claude-powered web-search briefing on the
 * company behind this job.
 *
 * Shape differs from the other AI panels: it's not versioned, it's
 * shared-cache-backed (the same company's briefing serves all users),
 * and it has three distinct states rather than a single generate-and-
 * display flow:
 *
 *   1. Pristine (404 from GET) — never researched. Show a CTA.
 *   2. Cached — briefing exists. Show it, plus a staleness hint and a
 *      Refresh button if it's past expiry.
 *   3. Ineligible (400 from GET) — job has no company name. Show a
 *      short message pointing the user at the job detail to fix it.
 *
 * Web_search takes ~15–30 seconds end-to-end. We set that expectation
 * in the pending copy so the user doesn't think the app has hung.
 */
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
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';
import { useUserQuota } from '@/api/quota';
import { UserQuotaCaption } from './UserQuotaCaption';
import { safeHref } from '@/utils/safeHref';

export function CompanyResearchPanel({
  jobId,
  companyName,
}: {
  jobId: string;
  companyName: string;
}) {
  const query = useCompanyResearch(jobId);
  const generate = useGenerateCompanyResearch(jobId);
  const quota = useUserQuota('company_research');

  const status404 =
    query.isError && query.error instanceof ApiError && query.error.status === 404;
  const status400 =
    query.isError && query.error instanceof ApiError && query.error.status === 400;
  const otherError =
    query.isError && !status404 && !status400 ? query.error : null;

  // Header hint mirrors the staleness logic the CacheStatus chip uses
  // inside the body, so the collapsed state tells the user what they
  // need to know without expanding.
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

  // While the initial GET resolves, render a minimal body — the
  // collapsed header already shows "Loading…" via the hint.
  if (query.isLoading) {
    return (
      <CollapsibleSection title="Company research" hint={hint}>
        <p className="text-sm text-ink-3">Loading…</p>
      </CollapsibleSection>
    );
  }

  return (
    <CollapsibleSection title="Company research" hint={hint}>
      {query.data && (
        <div className="flex items-center justify-end mb-3">
          <CacheStatus data={query.data} />
        </div>
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
            className="mb-btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={() => generate.mutate()}
            disabled={generate.isPending || quota.atLimit}
            title={quota.atLimit ? 'No researches left this month — upgrade for unlimited' : undefined}
          >
            <Globe size={14} />
            Research company
          </button>
          <UserQuotaCaption resource="company_research" />
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
          atLimit={quota.atLimit}
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

function CacheStatus({ data }: { data: CompanyResearch }) {
  const now = Date.now();
  const expires = Date.parse(data.expires_at);
  const cached = Date.parse(data.cached_at);
  const stale = expires < now;
  const ageMs = now - cached;
  const label = data.fresh
    ? 'Just researched'
    : stale
      ? `Cached ${relTime(ageMs)} ago · stale`
      : `Cached ${relTime(ageMs)} ago`;
  return (
    <div
      className={`text-xs ${stale ? 'text-rust' : 'text-ink-3'}`}
      title={`Cached at ${new Date(data.cached_at).toLocaleString()}, expires ${new Date(data.expires_at).toLocaleString()}`}
    >
      {label}
    </div>
  );
}

export function relTime(ms: number): string {
  // Tiny inline formatter — Intl.RelativeTimeFormat would be nicer but
  // we only need one direction and three buckets.
  const minutes = Math.round(ms / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.round(hours / 24);
  return `${days}d`;
}

function BriefingView({
  data,
  onRefresh,
  refreshing,
  atLimit,
}: {
  data: CompanyResearch;
  onRefresh: () => void;
  refreshing: boolean;
  atLimit: boolean;
}) {
  const [open, setOpen] = useState(true);
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(data.briefing);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1 text-xs text-ink-3 hover:text-ink"
        >
          <ChevronDown
            size={14}
            className={`transition-transform ${open ? '' : '-rotate-90'}`}
          />
          {open ? 'Hide briefing' : 'Show briefing'}
        </button>
        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={copy}
            className="mb-btn-ghost py-1 px-2 text-xs flex items-center gap-1"
            title="Copy briefing"
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button
            onClick={onRefresh}
            className="mb-btn-ghost py-1 px-2 text-xs flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={refreshing || atLimit}
            title={atLimit ? 'No researches left this month — upgrade for unlimited' : 'Run a fresh research pass'}
          >
            <RefreshCw
              size={12}
              className={refreshing ? 'animate-spin' : ''}
            />
            Refresh
          </button>
        </div>
      </div>

      {open && (
        <>
          <div className="rounded-lg border border-border bg-cream/50 px-4 py-3 text-sm text-ink whitespace-pre-wrap leading-relaxed">
            {data.briefing || '(empty briefing — try Refresh)'}
          </div>

          {data.sources.length > 0 && (
            <div>
              <div className="mb-label mb-1">Sources</div>
              <ul className="space-y-1 text-xs">
                {data.sources.map((url) => {
                  // Sources come from Claude+web_search output. The model
                  // is generally well-behaved but a prompt-injected job
                  // description could theoretically coax it into emitting
                  // a `javascript:` URL — safeHref drops anything that
                  // isn't http/https/mailto.
                  const safe = safeHref(url);
                  if (!safe) return null;
                  return (
                    <li key={url} className="truncate">
                      <a
                        href={safe}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-ink-2 hover:text-ink"
                      >
                        <ExternalLink size={11} className="shrink-0" />
                        <span className="truncate">{url}</span>
                      </a>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
