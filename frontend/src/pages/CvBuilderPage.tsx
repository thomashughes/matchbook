/**
 * /cv — CV builder. Generate, review, download, regenerate.
 *
 * The user never edits the markdown directly. The output is a finished
 * CV they grab and send. Flow:
 *   1. Idle → Start → Phase 1 (Claude's clarifying questions + the
 *      contact-info picker with skip toggles per field).
 *   2. Generating → spinner + hallucination warning.
 *   3. Preview → full-fidelity PDF embedded in an iframe, identical to
 *      the download. Post-preview: "How does this CV look?" with a
 *      regenerate path if they want changes, and a "Rebuild profile
 *      from this CV" button that re-parses the CV into the user's
 *      typed profile fields.
 *
 * Versions are collapsible cards (mirrors the cover-letter panel UX).
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Download,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  UserCog,
  X,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';
import {
  useBillingStatus,
  useCvPhaseOne,
  useCvPhaseTwo,
  useCvQuota,
  useCvVersions,
  useDeleteCvVersion,
  useProfile,
  useRebuildProfileFromCv,
} from '@/api/hooks';
import type {
  CvAnswer,
  CvQuestion,
  CvTone,
  CvVersion,
} from '@/types/models';

// --- Contact-info form config --------------------------------------------

// Fixed set of contact fields shown to every candidate. The frontend
// owns this rather than Claude, so users always see the same choices
// in the same order, with consistent validation + skip toggles.
type ContactKey =
  | 'email'
  | 'phone'
  | 'location'
  | 'linkedin'
  | 'github'
  | 'portfolio';

const CONTACT_FIELDS: Array<{
  key: ContactKey;
  label: string;
  placeholder: string;
}> = [
  { key: 'email', label: 'Email', placeholder: 'you@example.co.uk' },
  { key: 'phone', label: 'Phone', placeholder: '+44 7700 900000' },
  { key: 'location', label: 'Location', placeholder: 'London, UK' },
  {
    key: 'linkedin',
    label: 'LinkedIn',
    placeholder: 'linkedin.com/in/jane-doe',
  },
  { key: 'github', label: 'GitHub', placeholder: 'github.com/jane-doe' },
  { key: 'portfolio', label: 'Portfolio', placeholder: 'janedoe.com' },
];

type ContactState = Record<ContactKey, { value: string; include: boolean }>;

// Custom rows the user added themselves — same include flag so a user
// can stage an entry, toggle it off, and keep it around without it
// being rendered on the CV.
type CustomRow = { label: string; value: string; include: boolean };

function blankContact(): ContactState {
  const obj = {} as ContactState;
  for (const f of CONTACT_FIELDS) obj[f.key] = { value: '', include: true };
  return obj;
}

// --- Page -----------------------------------------------------------------

export function CvBuilderPage() {
  const prof = useProfile();
  const billing = useBillingStatus();
  const quota = useCvQuota();
  const versions = useCvVersions();
  const phaseOne = useCvPhaseOne();
  const phaseTwo = useCvPhaseTwo();
  const nav = useNavigate();

  const [currentVersionId, setCurrentVersionId] = useState<string | null>(null);
  const [phase, setPhase] = useState<'idle' | 'questions' | 'generating' | 'preview'>(
    'idle',
  );
  const [questions, setQuestions] = useState<CvQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [extraNotes, setExtraNotes] = useState('');
  const [tone, setTone] = useState<CvTone>('professional');
  const [contact, setContact] = useState<ContactState>(blankContact());
  const [customContacts, setCustomContacts] = useState<CustomRow[]>([]);
  const [regenOpen, setRegenOpen] = useState(false);

  // Auto-switch to the preview of the latest version once data loads.
  // This keeps navigation cheap: returning to /cv drops you straight
  // into the most recent CV rather than re-showing the Start button.
  useEffect(() => {
    if (
      versions.data &&
      versions.data.length > 0 &&
      currentVersionId === null &&
      phase === 'idle'
    ) {
      setCurrentVersionId(versions.data[0].id);
      setPhase('preview');
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
      setContact(blankContact());
      setCustomContacts([]);
      setPhase('questions');
    } catch (e) {
      console.error(e);
    }
  }

  async function submit(regenReason: string | null) {
    // Build the contact object: only include fields with include=true
    // AND a non-empty value. Empty-but-included fields are treated as
    // skipped (Claude will omit them from the finished CV).
    const contactPayload: Record<string, unknown> = {};
    for (const f of CONTACT_FIELDS) {
      const c = contact[f.key];
      if (c.include && c.value.trim()) {
        contactPayload[f.key] = c.value.trim();
      }
    }
    // Custom rows: keep only those with both a label AND a value, and
    // where the user hasn't toggled skip. We pass as `extra` — matches
    // the backend CvContact.extra list shape.
    const customItems = customContacts
      .filter((c) => c.include && c.label.trim() && c.value.trim())
      .map((c) => ({ label: c.label.trim(), value: c.value.trim() }));
    if (customItems.length > 0) {
      contactPayload.extra = customItems;
    }

    const body = {
      answers: questions.map<CvAnswer>((q) => ({
        id: q.id,
        question: q.text,
        answer: answers[q.id] ?? '',
      })),
      tone,
      extra_notes: extraNotes,
      regenerate_reason: regenReason,
      // Only include the contact object when at least one field was
      // provided. An empty object would make Claude think we're
      // deliberately producing a CV with no contact details.
      ...(Object.keys(contactPayload).length > 0
        ? { contact: contactPayload }
        : {}),
    };
    setPhase('generating');
    try {
      const row = await phaseTwo.mutateAsync(body as Parameters<typeof phaseTwo.mutateAsync>[0]);
      setCurrentVersionId(row.id);
      setPhase('preview');
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
    <div className="max-w-5xl mx-auto px-7 py-8 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink">CV builder</h1>
          <p className="text-sm text-ink-muted mt-1">
            A tailored CV, written from your profile and your answers —
            ready to download.{' '}
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

      {/* Start */}
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

      {/* Questions */}
      {phase === 'questions' && (
        <QuestionsForm
          questions={questions}
          answers={answers}
          extraNotes={extraNotes}
          tone={tone}
          contact={contact}
          customContacts={customContacts}
          onAnswerChange={(id, v) => setAnswers((a) => ({ ...a, [id]: v }))}
          onExtraChange={setExtraNotes}
          onToneChange={setTone}
          onContactValue={(k, v) =>
            setContact((s) => ({ ...s, [k]: { ...s[k], value: v } }))
          }
          onContactSkip={(k, skipped) =>
            setContact((s) => ({ ...s, [k]: { ...s[k], include: !skipped } }))
          }
          onAddCustomContact={() =>
            setCustomContacts((arr) => [
              ...arr,
              { label: '', value: '', include: true },
            ])
          }
          onRemoveCustomContact={(i) =>
            setCustomContacts((arr) => arr.filter((_, idx) => idx !== i))
          }
          onCustomContactChange={(i, patch) =>
            setCustomContacts((arr) =>
              arr.map((row, idx) => (idx === i ? { ...row, ...patch } : row)),
            )
          }
          onCancel={() => setPhase('idle')}
          onSubmit={() => submit(null)}
          busy={phaseTwo.isPending}
        />
      )}

      {/* Generating */}
      {phase === 'generating' && <GeneratingPanel />}

      {/* Preview */}
      {phase === 'preview' && current && (
        <PreviewView
          current={current}
          versions={versions.data ?? []}
          currentProfileVersion={prof.data.profile_version}
          canGenerate={canGenerate}
          remaining={remaining === undefined ? 0 : remaining}
          onSelectVersion={setCurrentVersionId}
          onRequestRegenerate={() => setRegenOpen(true)}
          onAfterProfileRebuild={() => nav('/profile')}
        />
      )}

      {regenOpen && (
        <RegenerateModal
          tone={tone}
          remaining={remaining === undefined ? 0 : remaining}
          onToneChange={setTone}
          onClose={() => setRegenOpen(false)}
          onConfirm={(reason) => {
            setRegenOpen(false);
            if (questions.length === 0) {
              // No cached phase-1 state — re-fetch questions first,
              // then let the user update answers (pre-populated where
              // possible). For v1 we just go through phase-1 again.
              void startQuestions();
            } else {
              void submit(reason);
            }
          }}
        />
      )}

      {phaseTwo.isError && (
        <div className="text-sm text-rust bg-rust-light rounded-lg px-3 py-2">
          Couldn't generate — please try again in a moment. No credit
          was consumed.
        </div>
      )}
    </div>
  );
}

// --- Panels ---------------------------------------------------------------

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
            Claude will ask 10–14 targeted questions based on your
            uploaded CV. You'll also pick which contact links to show.
            The result is a finished CV you can download and send — no
            editing required.
          </p>
          <HallucinationWarning />
          <button
            className="mb-btn-primary mt-4"
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

function HallucinationWarning() {
  return (
    <div
      className="text-xs text-ink-muted rounded-lg px-3 py-2 flex items-start gap-2"
      style={{ background: 'var(--parchment)' }}
    >
      <AlertTriangle size={14} className="mt-0.5 shrink-0 text-rust" />
      <div>
        <strong>Claude can make mistakes.</strong> Read the finished CV
        carefully — check names, dates, numbers, and company details
        before sending it anywhere.
      </div>
    </div>
  );
}

function GeneratingPanel() {
  return (
    <div className="mb-card flex flex-col items-center gap-4 py-12">
      <Loader2 size={32} className="animate-spin text-teal" />
      <div className="text-sm text-ink-2">
        Writing your CV — this usually takes 20–40 seconds.
      </div>
      <div className="text-xs text-ink-muted text-center max-w-md">
        When it's ready, read it closely. Claude can make mistakes
        even with everything you've told it — check every name, date,
        and number before sending.
      </div>
    </div>
  );
}

function QuestionsForm({
  questions,
  answers,
  extraNotes,
  tone,
  contact,
  customContacts,
  onAnswerChange,
  onExtraChange,
  onToneChange,
  onContactValue,
  onContactSkip,
  onAddCustomContact,
  onRemoveCustomContact,
  onCustomContactChange,
  onCancel,
  onSubmit,
  busy,
}: {
  questions: CvQuestion[];
  answers: Record<string, string>;
  extraNotes: string;
  tone: CvTone;
  contact: ContactState;
  customContacts: CustomRow[];
  onAnswerChange: (id: string, value: string) => void;
  onExtraChange: (v: string) => void;
  onToneChange: (t: CvTone) => void;
  onContactValue: (k: ContactKey, v: string) => void;
  onContactSkip: (k: ContactKey, skipped: boolean) => void;
  onAddCustomContact: () => void;
  onRemoveCustomContact: (index: number) => void;
  onCustomContactChange: (index: number, patch: Partial<CustomRow>) => void;
  onCancel: () => void;
  onSubmit: () => void;
  busy: boolean;
}) {
  const filledCount = questions.filter(
    (q) => (answers[q.id] ?? '').trim(),
  ).length;
  return (
    <div className="mb-card space-y-6">
      <div>
        <div className="mb-display text-lg mb-1">Tell Claude about you</div>
        <p className="text-sm text-ink-2">
          {filledCount} of {questions.length} answered. The more you
          share, the better the rewrite — we try to avoid placeholder
          text in the finished CV.
        </p>
      </div>

      <HallucinationWarning />

      {/* Contact-info block — always first, so the candidate can see
          exactly what will appear in the contact line of the finished
          CV. Fixed fields + custom additions for anything the picker
          doesn't cover (Stack Overflow, personal blog, etc). */}
      <div>
        <div className="mb-label mb-2">Contact details</div>
        <div className="text-xs text-ink-muted mb-3">
          These appear at the top of your CV. Untick any you don't
          want shown. Leave the value empty to skip.
        </div>
        <div className="space-y-2">
          {CONTACT_FIELDS.map((f) => {
            const entry = contact[f.key];
            return (
              <div key={f.key} className="flex items-center gap-3">
                <div className="w-24 text-xs text-ink-2 shrink-0">
                  {f.label}
                </div>
                <input
                  className="mb-input flex-1"
                  placeholder={f.placeholder}
                  value={entry.value}
                  onChange={(e) => onContactValue(f.key, e.target.value)}
                  disabled={!entry.include}
                  style={!entry.include ? { opacity: 0.5 } : undefined}
                />
                <label className="text-xs text-ink-muted flex items-center gap-1 shrink-0">
                  <input
                    type="checkbox"
                    checked={!entry.include}
                    onChange={(e) => onContactSkip(f.key, e.target.checked)}
                  />
                  skip
                </label>
              </div>
            );
          })}

          {/* User-added custom contact rows. Label + value + skip per
              row. The X button removes the row entirely. */}
          {customContacts.map((row, i) => (
            <div key={i} className="flex items-center gap-3">
              <input
                className="mb-input w-24 shrink-0 text-xs"
                placeholder="Label"
                value={row.label}
                onChange={(e) =>
                  onCustomContactChange(i, { label: e.target.value })
                }
                disabled={!row.include}
                style={!row.include ? { opacity: 0.5 } : undefined}
              />
              <input
                className="mb-input flex-1"
                placeholder="e.g. stackoverflow.com/users/..."
                value={row.value}
                onChange={(e) =>
                  onCustomContactChange(i, { value: e.target.value })
                }
                disabled={!row.include}
                style={!row.include ? { opacity: 0.5 } : undefined}
              />
              <label className="text-xs text-ink-muted flex items-center gap-1 shrink-0">
                <input
                  type="checkbox"
                  checked={!row.include}
                  onChange={(e) =>
                    onCustomContactChange(i, { include: !e.target.checked })
                  }
                />
                skip
              </label>
              <button
                type="button"
                className="p-1.5 rounded hover:bg-rust-light text-ink-3 hover:text-rust shrink-0"
                onClick={() => onRemoveCustomContact(i)}
                title="Remove"
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>

        <button
          type="button"
          className="mt-3 text-xs text-teal inline-flex items-center gap-1 hover:underline"
          onClick={onAddCustomContact}
        >
          <Plus size={12} />
          Add another contact (e.g. Stack Overflow, blog, Instagram)
        </button>
      </div>

      {/* Claude's clarifying questions */}
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
            Extra context, constraints, or preferences. Optional.
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

// --- Preview view ---------------------------------------------------------

/**
 * Fetch the PDF for a given CV version with auth, and hold it in a
 * blob-URL ref so the iframe src + download button both work without
 * re-fetching. Re-runs whenever `cvId` changes.
 */
function usePdfBlob(cvId: string | undefined) {
  const token = useAuthStore((s) => s.accessToken);
  const [url, setUrl] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const urlRef = useRef<string | null>(null);

  useEffect(() => {
    if (!cvId || !token) return;
    let cancelled = false;
    setLoading(true);
    setErr(null);

    fetch(`/api/v1/cv/${cvId}/pdf`, {
      headers: { Authorization: `Bearer ${token}` },
      credentials: 'include',
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`PDF fetch ${res.status}`);
        const blob = await res.blob();
        if (cancelled) return;
        const u = URL.createObjectURL(blob);
        // Revoke any prior blob URL to avoid leaking memory on version
        // switch.
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        urlRef.current = u;
        setUrl(u);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setErr((e as Error).message);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [cvId, token]);

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current);
        urlRef.current = null;
      }
    };
  }, []);

  return { url, err, loading };
}

function PreviewView({
  current,
  versions,
  currentProfileVersion,
  canGenerate,
  remaining,
  onSelectVersion,
  onRequestRegenerate,
  onAfterProfileRebuild,
}: {
  current: CvVersion;
  versions: CvVersion[];
  currentProfileVersion: number;
  canGenerate: boolean;
  // null = unlimited (grandfathered). Number = remaining credits this
  // cycle (0 disables generate buttons).
  remaining: number | null;
  onSelectVersion: (id: string) => void;
  onRequestRegenerate: () => void;
  onAfterProfileRebuild: () => void;
}) {
  const remove = useDeleteCvVersion();
  const rebuild = useRebuildProfileFromCv();
  const pdf = usePdfBlob(current.id);
  const [feedback, setFeedback] = useState<'idle' | 'liked' | 'disliked'>(
    'idle',
  );

  // Reset feedback when switching to a different version.
  useEffect(() => {
    setFeedback('idle');
  }, [current.id]);

  function downloadPdf() {
    if (!pdf.url) return;
    const a = document.createElement('a');
    a.href = pdf.url;
    a.download = `cv-v${current.version}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  const stale = current.profile_version !== currentProfileVersion;

  return (
    <div className="space-y-4">
      {/* Version list — collapsible, mirroring cover-letter cards */}
      <VersionList
        versions={versions}
        currentId={current.id}
        currentProfileVersion={currentProfileVersion}
        onSelect={onSelectVersion}
        onDelete={(id) => {
          if (
            window.confirm('Delete this CV version? This cannot be undone.')
          ) {
            remove.mutate(id, {
              onSuccess: () => {
                // Reloading resets state back to "auto-open latest".
                window.location.reload();
              },
            });
          }
        }}
      />

      {stale && (
        <div
          className="rounded-lg px-3 py-2 text-sm flex items-center gap-2"
          style={{ background: 'var(--parchment)' }}
        >
          <span className="text-rust font-medium">Previous profile.</span>
          <span className="text-ink-2">
            This CV was generated against an earlier profile. Regenerate
            to reflect your current profile.
          </span>
        </div>
      )}

      <HallucinationWarning />

      {/* Toolbar */}
      <div
        className="rounded-xl px-4 py-3 flex items-center justify-between flex-wrap gap-2"
        style={{
          background: 'var(--card)',
          border: '0.5px solid var(--border)',
        }}
      >
        <div className="text-xs text-ink-muted">
          Preview of <strong>v{current.version}</strong>. This is exactly
          what the PDF will look like.
        </div>
        <div className="flex items-center gap-2">
          <button
            className="mb-btn-primary text-xs"
            onClick={downloadPdf}
            disabled={!pdf.url || pdf.loading}
          >
            {pdf.loading ? (
              <>
                <Loader2 size={12} className="animate-spin mr-1" />
                Preparing…
              </>
            ) : (
              <>
                <Download size={12} className="mr-1" />
                Download PDF
              </>
            )}
          </button>
        </div>
      </div>

      {/* PDF preview — the browser's native renderer handles pagination,
          fonts, layout. The user sees two pages if the CV runs long. */}
      <div
        className="rounded-xl overflow-hidden"
        style={{
          background: 'var(--parchment)',
          border: '0.5px solid var(--border)',
          height: '900px',
        }}
      >
        {pdf.loading && (
          <div className="h-full flex items-center justify-center text-ink-2">
            <Loader2 size={24} className="animate-spin" />
          </div>
        )}
        {pdf.err && !pdf.loading && (
          <div className="h-full flex items-center justify-center text-rust text-sm p-4 text-center">
            Couldn't load the PDF preview. {pdf.err}. Try refreshing the
            page.
          </div>
        )}
        {pdf.url && !pdf.loading && !pdf.err && (
          <iframe
            title={`CV v${current.version}`}
            src={pdf.url}
            className="w-full h-full"
            style={{ border: 'none' }}
          />
        )}
      </div>

      {/* Feedback block — ask once per version. */}
      {feedback === 'idle' && (
        <div
          className="rounded-xl px-5 py-4 flex items-center justify-between flex-wrap gap-3"
          style={{
            background: 'var(--card)',
            border: '0.5px solid var(--border)',
          }}
        >
          <div className="text-sm text-ink">
            Happy with this CV? You can download it, regenerate, or use
            it as the basis for your profile.
          </div>
          <div className="flex items-center gap-2">
            <button
              className="mb-btn-primary text-xs"
              onClick={() => setFeedback('liked')}
            >
              <Check size={12} className="mr-1" />
              Yes, looks good
            </button>
            <button
              className="mb-btn-secondary text-xs"
              onClick={() => setFeedback('disliked')}
            >
              Needs changes
            </button>
          </div>
        </div>
      )}

      {feedback === 'disliked' && (
        <div
          className="rounded-xl px-5 py-4"
          style={{
            background: 'var(--card)',
            border: '0.5px solid var(--border)',
          }}
        >
          <div className="text-sm text-ink mb-2">
            What's not working? Tell us in the regenerate dialog and
            Claude will use your feedback to produce a different version.
          </div>
          <div
            className="text-xs text-ink-muted mb-3 rounded-lg px-3 py-2 flex items-start gap-2"
            style={{ background: 'var(--parchment)' }}
          >
            <AlertTriangle size={12} className="mt-0.5 shrink-0 text-rust" />
            {remaining === null
              ? 'Regenerating uses 1 credit (you have unlimited generations on your plan).'
              : `Regenerating uses 1 of your ${remaining} remaining credits this cycle.`}
          </div>
          <div className="flex items-center gap-2">
            <button
              className="mb-btn-primary text-xs"
              onClick={onRequestRegenerate}
              disabled={!canGenerate}
            >
              <RefreshCw size={12} className="mr-1" />
              Regenerate (1 credit)
            </button>
            <button
              className="mb-btn-secondary text-xs"
              onClick={() => setFeedback('idle')}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {feedback === 'liked' && (
        <div
          className="rounded-xl px-5 py-4 space-y-3"
          style={{
            background: 'var(--card)',
            border: '0.5px solid var(--border)',
          }}
        >
          <div className="flex items-start gap-3">
            <UserCog size={20} className="text-teal mt-0.5 shrink-0" />
            <div className="flex-1">
              <div className="text-sm font-medium text-ink mb-1">
                Rebuild your profile from this CV
              </div>
              <p className="text-xs text-ink-muted mb-3">
                Use this CV as the new source for your profile — skills,
                seniority, salary, and so on. Your onboarding answers
                stay the same, so you don't need to re-answer anything.
                Existing jobs, cover letters, and older CVs stay but
                will be marked as being based on a previous profile.
              </p>
              <button
                className="mb-btn-secondary text-xs"
                onClick={() =>
                  rebuild.mutate(current.id, {
                    onSuccess: onAfterProfileRebuild,
                  })
                }
                disabled={rebuild.isPending}
              >
                {rebuild.isPending ? (
                  <>
                    <Loader2 size={12} className="animate-spin mr-1" />
                    Rebuilding…
                  </>
                ) : (
                  'Rebuild profile from this CV'
                )}
              </button>
              {rebuild.isError && (
                <div className="text-xs text-rust mt-2">
                  Couldn't rebuild. Try again.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Generate new version button, always visible under preview */}
      <div className="pt-2">
        <button
          className="mb-btn-secondary text-xs"
          onClick={onRequestRegenerate}
          disabled={!canGenerate}
        >
          <RefreshCw size={12} className="mr-1" />
          {remaining === 0
            ? 'No credits left'
            : 'Generate a new version'}
        </button>
      </div>
    </div>
  );
}

// --- Version list (collapsible, mirrors CoverLetterPanel LetterCard) -----

function VersionList({
  versions,
  currentId,
  currentProfileVersion,
  onSelect,
  onDelete,
}: {
  versions: CvVersion[];
  currentId: string;
  currentProfileVersion: number;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="space-y-2">
      {versions.map((v) => {
        const stale = v.profile_version !== currentProfileVersion;
        const isCurrent = v.id === currentId;
        return (
          <VersionRow
            key={v.id}
            version={v}
            stale={stale}
            isCurrent={isCurrent}
            onSelect={() => onSelect(v.id)}
            onDelete={() => onDelete(v.id)}
          />
        );
      })}
    </div>
  );
}

function VersionRow({
  version,
  stale,
  isCurrent,
  onSelect,
  onDelete,
}: {
  version: CvVersion;
  stale: boolean;
  isCurrent: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  // Each row is a clickable header — clicking selects that version for
  // preview. A small chevron hints at collapse behaviour; we don't
  // embed the CV body inside the row (the preview already shows it
  // above), we just let the row flip between "expanded" metadata and
  // collapsed title. This keeps the list compact for users with many
  // versions.
  const [open, setOpen] = useState(isCurrent);
  useEffect(() => {
    if (isCurrent) setOpen(true);
  }, [isCurrent]);

  return (
    <div
      className={`rounded-lg overflow-hidden border ${
        isCurrent ? 'border-ink' : 'border-border'
      }`}
      style={{ background: isCurrent ? 'var(--parchment)' : 'var(--card)' }}
    >
      <button
        type="button"
        onClick={() => {
          setOpen((v) => !v);
          onSelect();
        }}
        className="w-full flex items-center justify-between p-3 hover:bg-cream/80 transition"
      >
        <div className="flex items-center gap-2 text-xs text-ink-3">
          <ChevronDown
            size={14}
            className={`transition-transform ${open ? '' : '-rotate-90'}`}
          />
          <span className="font-medium text-ink-2">v{version.version}</span>
          <span>·</span>
          <span className="capitalize">{version.tone}</span>
          <span>·</span>
          <span>{new Date(version.created_at).toLocaleString()}</span>
          {stale && (
            <span
              className="ml-1 px-1.5 py-0.5 rounded text-[10px]"
              style={{
                background: 'var(--rust-light, #f7e3d9)',
                color: 'var(--rust, #b0552d)',
              }}
            >
              Previous profile
            </span>
          )}
        </div>
        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="p-1.5 rounded hover:bg-rust-light text-ink-3 hover:text-rust"
            title="Delete"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </button>
      {open && version.regenerate_reason && (
        <div className="px-4 pb-3 pt-0 text-xs text-ink-muted">
          Regenerate reason: {version.regenerate_reason}
        </div>
      )}
    </div>
  );
}

// --- Regenerate modal -----------------------------------------------------

function RegenerateModal({
  remaining,
  tone,
  onToneChange,
  onClose,
  onConfirm,
}: {
  // null = unlimited (grandfathered accounts). Numbers are remaining
  // credits — 0 blocks submit, >0 allows it.
  remaining: number | null;
  tone: CvTone;
  onToneChange: (t: CvTone) => void;
  onClose: () => void;
  onConfirm: (reason: string) => void;
}) {
  const [reason, setReason] = useState('');
  const hasCredits = remaining === null || remaining > 0;
  const canSubmit = reason.trim().length >= 20 && hasCredits;

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
          {remaining === null ? (
            <>You have <strong>unlimited</strong> generations on your plan. This will use one credit from your quota (no effect for grandfathered accounts).</>
          ) : (
            <>
              You have <strong>{remaining}</strong> of 2 generations
              left this billing cycle. This will use one credit.
            </>
          )}
        </div>

        <div
          className="text-xs rounded-lg px-3 py-2 mb-4 flex items-start gap-2"
          style={{ background: 'var(--parchment)', color: 'var(--ink-2)' }}
        >
          <AlertTriangle size={14} className="mt-0.5 shrink-0 text-rust" />
          <div>
            Claude can hallucinate. When the new version arrives, check
            every name, date, and number before sending your CV.
          </div>
        </div>

        <label className="mb-label block mb-1">
          What would you like different this time?
        </label>
        <div className="text-xs text-ink-muted mb-2">
          Be specific — this guidance is fed directly to Claude. (min 20
          characters)
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
