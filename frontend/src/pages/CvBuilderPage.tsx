/**
 * /cv — CV builder: generate, edit, export.
 *
 * Four UI states:
 *   1. Locked — free tier sees the feature gated behind the upgrade CTA.
 *   2. Questions — Claude's 8-12 clarifying questions plus the tone
 *                  picker and an "Anything else?" free-text field.
 *   3. Generating — spinner while Phase 2 runs on the server.
 *   4. Editor — split source/preview view with a version sidebar.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowUp,
  Check,
  Copy,
  Download,
  FileDown,
  FileText,
  Info,
  Loader2,
  Sparkles,
  Trash2,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Link } from 'react-router-dom';
import {
  useBillingStatus,
  useCvPhaseOne,
  useCvPhaseTwo,
  useCvQuota,
  useCvVersions,
  useDeleteCvVersion,
  useProfile,
  useUpdateCvVersion,
} from '@/api/hooks';
import type {
  CvAnswer,
  CvQuestion,
  CvTone,
  CvVersion,
} from '@/types/models';

function wordCount(markdown: string): number {
  const cleaned = markdown
    .replace(/\[(?:VERIFY|REWRITE)\s*:\s*[^\]]*\]/gi, '')
    .trim();
  if (!cleaned) return 0;
  return cleaned.split(/\s+/).length;
}

function pagesEstimate(words: number): number {
  return Math.max(1, Math.round(words / 400));
}

const STALE_MESSAGE =
  'This CV was generated against a previous profile. Regenerate to reflect your latest skills and experience.';

export function CvBuilderPage() {
  const prof = useProfile();
  const billing = useBillingStatus();
  const quota = useCvQuota();
  const versions = useCvVersions();
  const phaseOne = useCvPhaseOne();
  const phaseTwo = useCvPhaseTwo();

  const [currentVersionId, setCurrentVersionId] = useState<string | null>(null);
  const [phase, setPhase] = useState<'idle' | 'questions' | 'generating' | 'editor'>('idle');
  const [questions, setQuestions] = useState<CvQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [extraNotes, setExtraNotes] = useState('');
  const [tone, setTone] = useState<CvTone>('professional');
  const [regenOpen, setRegenOpen] = useState(false);

  useEffect(() => {
    if (
      versions.data &&
      versions.data.length > 0 &&
      currentVersionId === null &&
      phase === 'idle'
    ) {
      setCurrentVersionId(versions.data[0].id);
      setPhase('editor');
    }
  }, [versions.data, currentVersionId, phase]);

  const planAllowsCv =
    billing.data?.plan === 'paid' || billing.data?.plan === 'paid_grandfathered';

  const remaining = quota.data?.remaining;
  const canGenerate =
    planAllowsCv && (remaining === null || (remaining ?? 0) > 0);

  const current = useMemo(() => {
    if (!versions.data || !currentVersionId) return null;
    return versions.data.find((v) => v.id === currentVersionId) ?? null;
  }, [versions.data, currentVersionId]);

  async function startQuestions() {
    try {
      const res = await phaseOne.mutateAsync();
      setQuestions(res.questions);
      const initial: Record<string, string> = {};
      for (const q of res.questions) {
        initial[q.id] = q.type === 'radio' ? q.options[0] ?? '' : '';
      }
      setAnswers(initial);
      setExtraNotes('');
      setPhase('questions');
    } catch (e) {
      console.error(e);
    }
  }

  async function submitPhaseTwo(regenReason: string | null) {
    const body = {
      answers: questions.map<CvAnswer>((q) => ({
        id: q.id,
        question: q.text,
        answer: answers[q.id] ?? '',
      })),
      tone,
      extra_notes: extraNotes,
      regenerate_reason: regenReason,
    };
    setPhase('generating');
    try {
      const row = await phaseTwo.mutateAsync(body);
      setCurrentVersionId(row.id);
      setPhase('editor');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e) {
      setPhase('questions');
    }
  }

  if (prof.isLoading || billing.isLoading) {
    return <div className="text-ink-3 p-8">Loading…</div>;
  }

  if (!prof.data) {
    return (
      <div className="p-8">
        <p className="text-ink-2">
          Finish onboarding before generating a CV.{' '}
          <Link to="/onboarding/cv" className="text-teal underline">
            Continue onboarding
          </Link>
          .
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-7 py-8">
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink">CV builder</h1>
          <p className="text-sm text-ink-muted mt-1">
            Craft a tailored, hallucination-checked CV from your profile
            and answers.{' '}
            {planAllowsCv && (
              <>
                Limit: <strong>2 generations per billing cycle</strong>.
              </>
            )}
          </p>
        </div>
        {planAllowsCv && typeof remaining === 'number' && (
          <div
            className="text-xs px-3 py-1.5 rounded-full"
            style={{ background: 'var(--parchment)', color: 'var(--ink-muted)' }}
          >
            {remaining} of 2 left
          </div>
        )}
      </div>

      {!planAllowsCv && (
        <div className="mb-card text-center py-10">
          <div className="mb-display text-xl mb-2">Paid feature</div>
          <p className="text-sm text-ink-2 max-w-md mx-auto mb-5">
            The CV builder uses Claude to rewrite your CV without the
            usual AI tells. Available on the Paid plan — 2 generations
            per billing cycle.
          </p>
          <Link to="/billing" className="mb-btn-primary inline-flex">
            Upgrade to use this feature
          </Link>
        </div>
      )}

      {planAllowsCv &&
        phase === 'idle' &&
        (versions.data?.length ?? 0) === 0 && (
          <StartPanel
            onStart={startQuestions}
            canGenerate={canGenerate}
            quotaRemaining={remaining}
            busy={phaseOne.isPending}
          />
        )}

      {phase === 'questions' && (
        <QuestionsForm
          questions={questions}
          answers={answers}
          extraNotes={extraNotes}
          tone={tone}
          onAnswerChange={(id, v) => setAnswers((a) => ({ ...a, [id]: v }))}
          onExtraChange={setExtraNotes}
          onToneChange={setTone}
          onCancel={() => setPhase('idle')}
          onSubmit={() => submitPhaseTwo(null)}
          busy={phaseTwo.isPending}
          error={null}
        />
      )}

      {phase === 'generating' && (
        <div className="mb-card flex flex-col items-center gap-4 py-12">
          <Loader2 size={32} className="animate-spin text-teal" />
          <div className="text-sm text-ink-2">
            Rewriting your CV — this usually takes 20–40 seconds.
          </div>
          <div className="text-xs text-ink-muted text-center max-w-md">
            When this finishes, carefully review every line. Claude can
            make mistakes — especially around dates, company names, and
            numbers. Anything marked <span className="font-mono">[VERIFY]</span>{' '}
            needs your attention.
          </div>
        </div>
      )}

      {phase === 'editor' && current && (
        <EditorView
          current={current}
          versions={versions.data ?? []}
          currentProfileVersion={prof.data.profile_version}
          canGenerate={canGenerate}
          remaining={remaining ?? 0}
          onSelectVersion={setCurrentVersionId}
          onRequestRegenerate={() => {
            if ((versions.data?.length ?? 0) === 0 || questions.length === 0) {
              void startQuestions();
            } else {
              setRegenOpen(true);
            }
          }}
        />
      )}

      {regenOpen && (
        <RegenerateModal
          tone={tone}
          remaining={remaining ?? 0}
          onToneChange={setTone}
          onClose={() => setRegenOpen(false)}
          onConfirm={(reason) => {
            setRegenOpen(false);
            void submitPhaseTwo(reason);
          }}
        />
      )}

      {phaseTwo.isError && (
        <div className="mt-4 text-sm text-rust bg-rust-light rounded-lg px-3 py-2">
          Couldn't generate — please try again in a moment. No credit
          was consumed.
        </div>
      )}
    </div>
  );
}

function StartPanel({
  onStart,
  canGenerate,
  quotaRemaining,
  busy,
}: {
  onStart: () => void;
  canGenerate: boolean;
  quotaRemaining: number | null | undefined;
  busy: boolean;
}) {
  return (
    <div className="mb-card">
      <div className="flex items-start gap-4">
        <div
          className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: 'var(--parchment)' }}
        >
          <FileText size={22} className="text-teal" />
        </div>
        <div className="flex-1">
          <div className="mb-display text-lg mb-1">Let's build your CV</div>
          <p className="text-sm text-ink-2 mb-4">
            Claude will ask 8–12 targeted questions based on the CV you
            uploaded. Your answers shape the rewrite. Expect tight,
            evidence-driven bullets and UK English.
          </p>
          <div
            className="text-xs text-ink-muted rounded-lg px-3 py-2 mb-4 flex items-start gap-2"
            style={{ background: 'var(--parchment)' }}
          >
            <AlertTriangle size={14} className="mt-0.5 shrink-0 text-rust" />
            <div>
              <strong>Please double-check everything.</strong> Claude can
              misstate dates, invent metrics, or misremember project
              scope. Anything marked <span className="font-mono">[VERIFY]</span>{' '}
              needs your confirmation before sending the CV anywhere.
            </div>
          </div>
          <button
            className="mb-btn-primary"
            onClick={onStart}
            disabled={!canGenerate || busy}
          >
            {busy ? (
              <>
                <Loader2 size={14} className="animate-spin mr-2" />
                Starting…
              </>
            ) : quotaRemaining === 0 ? (
              'No generations left this cycle'
            ) : (
              'Start'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function QuestionsForm({
  questions,
  answers,
  extraNotes,
  tone,
  onAnswerChange,
  onExtraChange,
  onToneChange,
  onCancel,
  onSubmit,
  busy,
  error,
}: {
  questions: CvQuestion[];
  answers: Record<string, string>;
  extraNotes: string;
  tone: CvTone;
  onAnswerChange: (id: string, value: string) => void;
  onExtraChange: (v: string) => void;
  onToneChange: (t: CvTone) => void;
  onCancel: () => void;
  onSubmit: () => void;
  busy: boolean;
  error: string | null;
}) {
  const filledCount = questions.filter((q) => (answers[q.id] ?? '').trim()).length;
  return (
    <div className="mb-card space-y-6">
      <div>
        <div className="mb-display text-lg mb-1">Tell Claude about you</div>
        <p className="text-sm text-ink-2">
          {filledCount} of {questions.length} answered. You can skip
          any — but the more you share, the sharper the rewrite.
        </p>
      </div>

      <div className="space-y-5">
        {questions.map((q, i) => (
          <div key={q.id}>
            <label className="mb-label block mb-1">
              {i + 1}. {q.text}
            </label>
            {q.hint && (
              <div className="text-xs text-ink-muted mb-2">{q.hint}</div>
            )}
            {q.type === 'text' && (
              <input
                className="mb-input"
                value={answers[q.id] ?? ''}
                onChange={(e) => onAnswerChange(q.id, e.target.value)}
              />
            )}
            {q.type === 'textarea' && (
              <textarea
                className="mb-input min-h-[90px]"
                value={answers[q.id] ?? ''}
                onChange={(e) => onAnswerChange(q.id, e.target.value)}
              />
            )}
            {q.type === 'radio' && (
              <div className="flex flex-wrap gap-2">
                {q.options.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => onAnswerChange(q.id, opt)}
                    className={`px-3 py-1.5 text-sm rounded-full border transition ${
                      answers[q.id] === opt
                        ? 'bg-ink text-white border-ink'
                        : 'bg-transparent border-border text-ink-2 hover:bg-parchment'
                    }`}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}

        <div>
          <label className="mb-label block mb-1">
            {questions.length + 1}. Anything else you'd like to include?
          </label>
          <div className="text-xs text-ink-muted mb-2">
            Extra context, constraints, or preferences Claude didn't ask
            about. Optional.
          </div>
          <textarea
            className="mb-input min-h-[90px]"
            value={extraNotes}
            onChange={(e) => onExtraChange(e.target.value)}
          />
        </div>

        <div>
          <label className="mb-label block mb-2">Tone</label>
          <div className="inline-flex rounded-full bg-parchment p-0.5">
            {(['professional', 'bold'] as CvTone[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => onToneChange(t)}
                className={`px-4 py-1.5 text-xs rounded-full capitalize transition ${
                  tone === t ? 'bg-ink text-white' : 'text-ink-2'
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          <div className="text-xs text-ink-muted mt-1">
            {tone === 'professional'
              ? 'Measured and understated. Good default.'
              : 'Sharper verbs and a more confident first-person voice.'}
          </div>
        </div>
      </div>

      {error && (
        <div className="text-sm text-rust bg-rust-light rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      <div className="flex items-center justify-between">
        <button className="mb-btn-secondary" onClick={onCancel}>
          Cancel
        </button>
        <button className="mb-btn-primary" onClick={onSubmit} disabled={busy}>
          {busy ? (
            <>
              <Loader2 size={14} className="animate-spin mr-2" />
              Generating…
            </>
          ) : (
            <>
              <Sparkles size={14} className="mr-2" />
              Generate CV (uses 1 credit)
            </>
          )}
        </button>
      </div>
    </div>
  );
}

function EditorView({
  current,
  versions,
  currentProfileVersion,
  canGenerate,
  remaining,
  onSelectVersion,
  onRequestRegenerate,
}: {
  current: CvVersion;
  versions: CvVersion[];
  currentProfileVersion: number;
  canGenerate: boolean;
  remaining: number;
  onSelectVersion: (id: string) => void;
  onRequestRegenerate: () => void;
}) {
  const update = useUpdateCvVersion();
  const remove = useDeleteCvVersion();

  const [src, setSrc] = useState(current.content_markdown);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    setSrc(current.content_markdown);
    setSavedAt(null);
  }, [current.id, current.content_markdown]);

  const stale = current.profile_version !== currentProfileVersion;
  const words = wordCount(src);
  const pages = pagesEstimate(words);
  const lengthWarning =
    words < 400 ? 'short' : words > 1000 ? 'long' : null;

  async function save() {
    await update.mutateAsync({ id: current.id, content_markdown: src });
    setSavedAt(Date.now());
  }

  async function copyMarkdown() {
    await navigator.clipboard.writeText(src);
  }

  function downloadPdf() {
    window.open(`/api/v1/cv/${current.id}/pdf`, '_blank');
  }

  function downloadMarkdown() {
    const blob = new Blob([src], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cv-v${current.version}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="grid grid-cols-[220px_1fr] gap-6 items-start">
      <aside className="space-y-2">
        <div className="mb-label">Versions</div>
        {versions.map((v) => {
          const s = v.profile_version !== currentProfileVersion;
          return (
            <div
              key={v.id}
              className={`rounded-lg border px-3 py-2 cursor-pointer transition ${
                v.id === current.id
                  ? 'border-ink bg-parchment'
                  : 'border-border hover:bg-parchment/50'
              }`}
              onClick={() => onSelectVersion(v.id)}
            >
              <div className="text-sm font-medium text-ink">v{v.version}</div>
              <div className="text-xs text-ink-muted">
                {new Date(v.created_at).toLocaleDateString()}
              </div>
              {s && (
                <div className="text-[10px] text-rust mt-1">
                  Previous profile
                </div>
              )}
            </div>
          );
        })}

        <button
          className="mb-btn-secondary w-full mt-4 text-xs"
          onClick={onRequestRegenerate}
          disabled={!canGenerate}
        >
          {remaining === 0 ? 'No credits left' : 'Generate new version'}
        </button>
      </aside>

      <div className="space-y-4">
        {stale && (
          <div
            className="rounded-lg px-3 py-2 text-sm flex items-start gap-2"
            style={{ background: 'var(--parchment)' }}
          >
            <Info size={14} className="mt-0.5 shrink-0" />
            {STALE_MESSAGE}
          </div>
        )}

        <div
          className="rounded-xl px-4 py-3 flex items-center justify-between flex-wrap gap-2"
          style={{
            background: 'var(--card)',
            border: '0.5px solid var(--border)',
          }}
        >
          <div className="text-xs text-ink-muted">
            {words} words · ~{pages} page{pages === 1 ? '' : 's'}{' '}
            {lengthWarning === 'short' && (
              <span className="text-rust">
                · under 400 — consider adding detail
              </span>
            )}
            {lengthWarning === 'long' && (
              <span className="text-rust">
                · over 1000 — consider trimming
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              className="mb-btn-secondary text-xs"
              onClick={copyMarkdown}
              title="Copy markdown"
            >
              <Copy size={12} className="mr-1" />
              Copy
            </button>
            <button
              className="mb-btn-secondary text-xs"
              onClick={downloadMarkdown}
              title="Download source"
            >
              <FileDown size={12} className="mr-1" />
              .md
            </button>
            <button
              className="mb-btn-primary text-xs"
              onClick={downloadPdf}
              title="Download PDF"
            >
              <Download size={12} className="mr-1" />
              PDF
            </button>
            <button
              className="mb-btn-secondary text-xs"
              onClick={() => {
                if (
                  window.confirm(
                    'Delete this CV version? This cannot be undone.',
                  )
                ) {
                  remove.mutate(current.id, {
                    onSuccess: () => {
                      window.location.reload();
                    },
                  });
                }
              }}
              title="Delete version"
            >
              <Trash2 size={12} />
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="mb-label mb-1">Markdown source</div>
            <textarea
              className="mb-input font-mono text-xs leading-relaxed"
              style={{ minHeight: 600 }}
              value={src}
              onChange={(e) => setSrc(e.target.value)}
              spellCheck
            />
            <div className="flex items-center gap-3 mt-2">
              <button
                className="mb-btn-primary"
                onClick={save}
                disabled={
                  update.isPending || src === current.content_markdown
                }
              >
                {update.isPending ? 'Saving…' : 'Save edits'}
              </button>
              {savedAt && (
                <span className="text-xs text-teal flex items-center gap-1">
                  <Check size={12} />
                  Saved
                </span>
              )}
            </div>
          </div>
          <div>
            <div className="mb-label mb-1">Preview</div>
            <div
              className="rounded-lg p-6"
              style={{
                background: '#fff',
                border: '0.5px solid var(--border)',
                minHeight: 600,
              }}
            >
              <CvMarkdownPreview source={src} />
            </div>
          </div>
        </div>

        <div className="text-xs text-ink-muted flex items-center gap-1">
          <ArrowUp size={12} />
          Tip: the PDF export strips [VERIFY] and [REWRITE] tags. Edit
          or address them before sending the CV.
        </div>
      </div>
    </div>
  );
}

function CvMarkdownPreview({ source }: { source: string }) {
  return (
    <div>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-2xl font-semibold text-ink mb-1 mt-0">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-sm uppercase tracking-wider text-ink-2 mt-5 mb-2 pb-1 border-b border-border">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-semibold text-ink mt-3 mb-1">
              {children}
            </h3>
          ),
          p: ({ children }) => (
            <p className="text-sm text-ink leading-relaxed my-1">
              {renderWithBadges(children)}
            </p>
          ),
          li: ({ children }) => (
            <li className="text-sm text-ink leading-relaxed">
              {renderWithBadges(children)}
            </li>
          ),
          ul: ({ children }) => (
            <ul className="list-disc ml-5 my-2 space-y-0.5">{children}</ul>
          ),
          em: ({ children }) => (
            <em className="not-italic text-ink-muted text-xs">
              {children}
            </em>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold text-ink">{children}</strong>
          ),
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}

function renderWithBadges(children: React.ReactNode): React.ReactNode {
  const arr = Array.isArray(children) ? children : [children];
  return arr.map((child, i) => {
    if (typeof child !== 'string') return <span key={i}>{child}</span>;
    const parts = child.split(/(\[(?:VERIFY|REWRITE)\s*:\s*[^\]]*\])/gi);
    return (
      <span key={i}>
        {parts.map((part, j) => {
          const m = /^\[(VERIFY|REWRITE)\s*:\s*([^\]]*)\]$/i.exec(part);
          if (!m) return part;
          const kind = m[1].toUpperCase();
          const note = m[2].trim();
          const isVerify = kind === 'VERIFY';
          return (
            <span
              key={j}
              className={`inline-block align-baseline px-1.5 py-0.5 mx-0.5 rounded text-[10px] font-medium ${
                isVerify
                  ? 'bg-rust-light text-rust'
                  : 'bg-teal-soft text-teal'
              }`}
              title={note}
            >
              {kind}: {note}
            </span>
          );
        })}
      </span>
    );
  });
}

function RegenerateModal({
  remaining,
  tone,
  onToneChange,
  onClose,
  onConfirm,
}: {
  remaining: number;
  tone: CvTone;
  onToneChange: (t: CvTone) => void;
  onClose: () => void;
  onConfirm: (reason: string) => void;
}) {
  const [reason, setReason] = useState('');
  const canSubmit = reason.trim().length >= 20 && remaining > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.4)' }}
      onClick={onClose}
    >
      <div
        className="mb-card w-full max-w-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-display text-lg mb-1">Regenerate your CV</div>
        <div className="text-sm text-ink-2 mb-4">
          You have <strong>{remaining}</strong> of 2 generations left
          this billing cycle. This will use one credit.
        </div>

        <div
          className="text-xs rounded-lg px-3 py-2 mb-4 flex items-start gap-2"
          style={{ background: 'var(--parchment)', color: 'var(--ink-2)' }}
        >
          <AlertTriangle size={14} className="mt-0.5 shrink-0 text-rust" />
          <div>
            Please review every word of the new version. Claude can
            hallucinate — check names, dates, numbers, and anything
            marked [VERIFY].
          </div>
        </div>

        <label className="mb-label block mb-1">
          What would you like different this time?
        </label>
        <div className="text-xs text-ink-muted mb-2">
          Be specific — this guidance is fed directly to Claude. (min
          20 characters)
        </div>
        <textarea
          className="mb-input min-h-[100px]"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Cut the manager-speak from the Profile section and lead with the fintech role instead of the agency one."
        />

        <div className="mt-4">
          <div className="mb-label mb-2">Tone</div>
          <div className="inline-flex rounded-full bg-parchment p-0.5">
            {(['professional', 'bold'] as CvTone[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => onToneChange(t)}
                className={`px-4 py-1.5 text-xs rounded-full capitalize transition ${
                  tone === t ? 'bg-ink text-white' : 'text-ink-2'
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 mt-6">
          <button className="mb-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="mb-btn-primary"
            onClick={() => onConfirm(reason.trim())}
            disabled={!canSubmit}
          >
            Generate (1 credit)
          </button>
        </div>
      </div>
    </div>
  );
}
