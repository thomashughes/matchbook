/**
 * JobDetailPage — the deep view for a single job.
 *
 * Layout follows handoff §3.5: score ring + radar hero, then three
 * explanation cards (strengths / weaknesses / red flags), then the
 * status selector + auto-saving notes, then the raw JD in a collapsible.
 *
 * Notes auto-save on 800ms debounce via PATCH; status changes save
 * immediately. We invalidate both the detail and list queries so the
 * dashboard stays fresh.
 */
import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, AlertTriangle, CheckCircle2, XCircle, RefreshCw, Trash2, ExternalLink } from 'lucide-react';
import { useJob, usePatchJob, useRescoreJob, useDeleteJob } from '@/api/hooks';
import { ScoreRing } from '@/components/ui/ScoreRing';
import { ScoreRadar } from '@/components/ui/ScoreRadar';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { CompanyResearchPanel } from '@/components/jobs/CompanyResearchPanel';
import { CoverLetterPanel } from '@/components/jobs/CoverLetterPanel';
import { FollowUpPanel } from '@/components/jobs/FollowUpPanel';
import { FormResponsePanel } from '@/components/jobs/FormResponsePanel';
import { InterviewPrepPanel } from '@/components/jobs/InterviewPrepPanel';
import { OutreachPanel } from '@/components/jobs/OutreachPanel';
import type { JobStatus } from '@/types/models';
import { useNavigate } from 'react-router-dom';

const STATUSES: JobStatus[] = ['saved', 'applied', 'interviewing', 'offer', 'rejected'];

export function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const job = useJob(id);
  const patch = usePatchJob(id ?? '');
  const rescore = useRescoreJob();
  const del = useDeleteJob();

  const [notes, setNotes] = useState('');
  const [showRaw, setShowRaw] = useState(false);
  const firstLoad = useRef(true);

  // Seed the textarea from server state once per job load, then let
  // the user drive it. Debounce-save below handles writeback.
  useEffect(() => {
    if (job.data && firstLoad.current) {
      setNotes(job.data.notes ?? '');
      firstLoad.current = false;
    }
  }, [job.data]);

  useEffect(() => {
    if (!job.data || firstLoad.current) return;
    if (notes === (job.data.notes ?? '')) return;
    const t = setTimeout(() => patch.mutate({ notes }), 800);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notes]);

  if (job.isLoading) return <div className="text-ink-3">Loading…</div>;
  if (!job.data) return <div className="text-ink-3">Job not found.</div>;

  const j = job.data;
  const s = j.score;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Link to="/jobs" className="inline-flex items-center gap-1 text-sm text-ink-2 hover:text-ink">
          <ArrowLeft size={14} /> All jobs
        </Link>
        <div className="flex gap-2">
          <button
            className="mb-btn-ghost"
            onClick={() => id && rescore.mutate(id)}
            disabled={rescore.isPending}
          >
            <RefreshCw size={14} className={rescore.isPending ? 'animate-spin' : ''} />
            Re-score
          </button>
          <button
            className="mb-btn-ghost text-rust"
            onClick={() => {
              if (!id) return;
              if (confirm('Delete this job? This cannot be undone.')) {
                del.mutate(id, { onSuccess: () => nav('/jobs') });
              }
            }}
          >
            <Trash2 size={14} /> Delete
          </button>
        </div>
      </div>

      <div className="mb-card">
        <div className="flex items-start gap-5">
          <ScoreRing score={s?.total_score ?? null} size={96} />
          <div className="flex-1 min-w-0">
            <div className="mb-display text-2xl">{j.title}</div>
            <div className="text-sm text-ink-2 mt-1">
              {j.company}{j.location ? ` · ${j.location}` : ''}
              {j.salary_raw ? ` · ${j.salary_raw}` : ''}
            </div>
            <div className="mt-3 flex items-center gap-2 flex-wrap">
              <StatusBadge status={j.status} />
              {j.source_url && (
                <a
                  href={j.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-ink-2 hover:text-ink inline-flex items-center gap-1"
                >
                  <ExternalLink size={12} /> Original posting
                </a>
              )}
            </div>
            {s?.summary && <p className="mt-4 text-sm text-ink-2 leading-relaxed">{s.summary}</p>}
          </div>
        </div>

        {s && (
          <div className="mt-5">
            <ScoreRadar score={s} />
          </div>
        )}
      </div>

      {s && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <ExplainCard
            tone="teal"
            icon={<CheckCircle2 size={16} className="text-teal" />}
            title="Strengths"
            items={s.strengths}
          />
          <ExplainCard
            tone="gold"
            icon={<XCircle size={16} className="text-gold" />}
            title="Weaknesses"
            items={s.weaknesses}
          />
          <ExplainCard
            tone="rust"
            icon={<AlertTriangle size={16} className="text-rust" />}
            title="Red flags"
            items={s.red_flags}
          />
        </div>
      )}

      <div className="mb-card">
        <div className="mb-label mb-2">Status</div>
        <div className="flex gap-2 flex-wrap">
          {STATUSES.map((st) => {
            // Selected buttons take the same colour scheme as StatusBadge
            // so the state reads the same here as everywhere else in the
            // product. Unselected buttons stay neutral so only the active
            // choice draws the eye.
            const active = j.status === st;
            const activeCls: Record<JobStatus, string> = {
              saved:        'bg-ink text-white',
              applied:      'bg-gold text-white',
              interviewing: 'bg-[#2b5d89] text-white',
              offer:        'bg-teal text-white',
              rejected:     'bg-rust text-white',
            };
            return (
              <button
                key={st}
                onClick={() => patch.mutate({ status: st })}
                className={`rounded-full px-3 py-1 text-sm capitalize transition ${
                  active ? activeCls[st] : 'bg-parchment text-ink-2 hover:text-ink'
                }`}
              >
                {st}
              </button>
            );
          })}
        </div>
      </div>

      <CoverLetterPanel jobId={j.id} />

      <OutreachPanel jobId={j.id} />

      <FormResponsePanel jobId={j.id} />

      <FollowUpPanel jobId={j.id} />

      <InterviewPrepPanel jobId={j.id} />

      <CompanyResearchPanel jobId={j.id} companyName={j.company} />

      {/* Notes sits after any AI-generated content (cover letter,
          outreach, form responses, follow-ups, interview prep,
          company research, etc.) so the user's own free-form context
          is the last editable block before the raw JD reference. */}
      <div className="mb-card">
        <div className="flex items-center justify-between mb-2">
          <div className="mb-label">Your notes</div>
          <span className="text-xs text-ink-3">
            {patch.isPending ? 'Saving…' : 'Auto-saves as you type'}
          </span>
        </div>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="mb-input min-h-[140px]"
          placeholder="Anything you want to remember about this role…"
        />
      </div>

      <div className="mb-card">
        <button
          onClick={() => setShowRaw((v) => !v)}
          className="text-sm text-ink-2 hover:text-ink"
        >
          {showRaw ? 'Hide' : 'Show'} full job description
        </button>
        {showRaw && (
          <pre className="mt-3 whitespace-pre-wrap text-sm text-ink-2 font-mono leading-relaxed">
            {j.description_raw}
          </pre>
        )}
      </div>
    </div>
  );
}

function ExplainCard({
  tone, icon, title, items,
}: {
  tone: 'teal' | 'gold' | 'rust';
  icon: React.ReactNode;
  title: string;
  items: string[] | null;
}) {
  const bg = tone === 'teal' ? 'bg-teal/5' : tone === 'gold' ? 'bg-gold/5' : 'bg-rust/5';
  return (
    <div className={`mb-card ${bg}`}>
      <div className="flex items-center gap-2 mb-3">
        {icon}
        <div className="mb-display text-base">{title}</div>
      </div>
      {items && items.length > 0 ? (
        <ul className="space-y-2 text-sm text-ink-2">
          {items.map((it, i) => <li key={i}>• {it}</li>)}
        </ul>
      ) : (
        <p className="text-sm text-ink-3">None noted.</p>
      )}
    </div>
  );
}
