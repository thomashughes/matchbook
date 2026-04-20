/**
 * FormResponsePanel — AI-drafted answers to individual application-form
 * questions.
 *
 * Shares the version-card pattern with CoverLetterPanel and OutreachPanel
 * (segmented chips in the row, copy + delete, only latest auto-opens),
 * but the primary control is different: it's a free-text <textarea>
 * rather than a segmented selector. The question *is* the knob — every
 * other AI action in the product has a small enum of shapes; this one
 * has an open input surface, so we give it the visual weight it needs.
 *
 * Optional word cap sits next to Generate. When empty, we send null and
 * the prompt instructs Claude to infer a sensible length from the
 * question's own framing (e.g. 'answer in 200 words' → 200, a one-line
 * eligibility check → one sentence).
 */
import { useState } from 'react';
import { Check, ChevronDown, Copy, Loader2, Send, Trash2 } from 'lucide-react';
import {
  useAIOutputs,
  useDeleteAIOutput,
  useGenerateFormResponse,
} from '@/api/hooks';
import type { JobAIOutput } from '@/types/models';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';
import { QuotaCaption } from './QuotaCaption';

// Keep the card-chip row readable when the question is long. 60 chars
// is a hair over a typical tweet-length preview — enough to recognise
// the question, short enough to sit inline with v-number and date.
const QUESTION_PREVIEW_MAX = 60;

function previewQuestion(q: unknown): string {
  if (typeof q !== 'string') return '';
  const trimmed = q.trim().replace(/\s+/g, ' ');
  return trimmed.length > QUESTION_PREVIEW_MAX
    ? trimmed.slice(0, QUESTION_PREVIEW_MAX - 1) + '…'
    : trimmed;
}

export function FormResponsePanel({ jobId }: { jobId: string }) {
  const [question, setQuestion] = useState('');
  // Stored as a string so the input can be empty without flickering to
  // 0. Parsed to a number (or null) only at submit time.
  const [maxWords, setMaxWords] = useState('');

  const list = useAIOutputs(jobId, 'form_response');
  const generate = useGenerateFormResponse(jobId);
  const remove = useDeleteAIOutput(jobId, 'form_response');

  const answers = list.data ?? [];
  const canGenerate = question.trim().length >= 3 && !generate.isPending;

  const count = answers.length;
  const hint = list.isLoading
    ? 'Loading…'
    : count === 0
      ? 'Not yet generated'
      : `${count} version${count === 1 ? '' : 's'}`;

  function submit() {
    const trimmed = question.trim();
    if (trimmed.length < 3) return;
    const parsed = maxWords.trim() ? parseInt(maxWords, 10) : NaN;
    // null signals "let Claude pick"; a finite integer in range gets
    // passed through as a hard cap. Out-of-range values fall back to
    // null rather than 422-ing the user — the backend re-validates.
    const capped =
      Number.isFinite(parsed) && parsed >= 20 && parsed <= 1000
        ? parsed
        : null;
    generate.mutate(
      { question: trimmed, max_words: capped },
      {
        onSuccess: () => {
          // Keep the question text so the user can tweak it and
          // regenerate, but clear the cap — a common tweak is 'try it
          // without the cap' or vice versa, and stale state there is
          // easy to miss.
          setMaxWords('');
        },
      },
    );
  }

  return (
    <CollapsibleSection title="Form response" hint={hint}>
      <div className="space-y-3 mb-4">
        <div>
          <div className="mb-label mb-1">Application-form question</div>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Paste one question from the form — e.g. 'Describe a time you led a team through a difficult change.'"
            className="mb-input min-h-[110px] text-sm leading-relaxed"
            aria-label="Application form question"
          />
        </div>

        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <div className="mb-label mb-1">Word cap (optional)</div>
            <input
              type="number"
              min={20}
              max={1000}
              value={maxWords}
              onChange={(e) => setMaxWords(e.target.value)}
              placeholder="Claude picks"
              className="mb-input py-1 text-sm w-32"
              aria-label="Word cap"
            />
          </div>

          <div className="ml-auto">
            <button
              className="mb-btn-primary flex items-center gap-2"
              onClick={submit}
              disabled={!canGenerate}
            >
              {generate.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Send size={14} />
              )}
              {generate.isPending
                ? 'Drafting…'
                : answers.length === 0
                  ? 'Draft answer'
                  : 'Draft another'}
            </button>
            <QuotaCaption jobId={jobId} resource="draft_form_response" />
          </div>
        </div>
      </div>

      {answers.length === 0 && !generate.isPending && (
        <p className="text-sm text-ink-3">
          Paste a single question from the application form and generate
          a tailored answer grounded in your profile and this job's
          description. Each draft is saved as its own version.
        </p>
      )}

      {answers.length > 0 && (
        <div className="space-y-3">
          {answers.map((a, i) => (
            <FormResponseCard
              key={a.id}
              output={a}
              defaultOpen={i === 0}
              onDelete={() => {
                if (confirm('Delete this answer? This cannot be undone.')) {
                  remove.mutate(a.id);
                }
              }}
            />
          ))}
        </div>
      )}

      {generate.isError && (
        <p className="text-sm text-rust mt-3">
          Couldn't generate — please try again in a moment.
        </p>
      )}
    </CollapsibleSection>
  );
}

function FormResponseCard({
  output,
  defaultOpen,
  onDelete,
}: {
  output: JobAIOutput;
  defaultOpen: boolean;
  onDelete: () => void;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [copied, setCopied] = useState(false);

  async function copy(e: React.MouseEvent) {
    e.stopPropagation();
    await navigator.clipboard.writeText(output.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  // params shape mirrors the backend body: { question: string,
  // max_words: number | null }. Coerce defensively so a legacy row
  // with a missing field doesn't crash the card.
  const qPreview = previewQuestion(output.params.question);
  const cap =
    typeof output.params.max_words === 'number'
      ? (output.params.max_words as number)
      : null;

  return (
    <div className="rounded-lg border border-border bg-cream/50 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between p-3 hover:bg-cream/80 transition text-left"
      >
        <div className="flex items-center gap-2 text-xs text-ink-3 min-w-0">
          <ChevronDown
            size={14}
            className={`shrink-0 transition-transform ${open ? '' : '-rotate-90'}`}
          />
          <span className="font-medium text-ink-2 shrink-0">
            v{output.version}
          </span>
          <span className="shrink-0">·</span>
          <span
            className="italic text-ink-2 truncate"
            title={
              typeof output.params.question === 'string'
                ? (output.params.question as string)
                : undefined
            }
          >
            {qPreview ? `"${qPreview}"` : '(no question recorded)'}
          </span>
          {cap !== null && (
            <>
              <span className="shrink-0">·</span>
              <span className="shrink-0">{cap}w cap</span>
            </>
          )}
          <span className="shrink-0">·</span>
          <span className="shrink-0">
            {new Date(output.created_at).toLocaleString()}
          </span>
        </div>
        <div
          className="flex items-center gap-1 shrink-0 ml-2"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={copy}
            className="p-1.5 rounded hover:bg-parchment text-ink-3 hover:text-ink"
            title="Copy"
            aria-label="Copy answer"
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="p-1.5 rounded hover:bg-rust-light text-ink-3 hover:text-rust"
            title="Delete"
            aria-label="Delete answer"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </button>
      {open && (
        <div className="px-4 pb-4 pt-1 text-sm text-ink whitespace-pre-wrap leading-relaxed">
          {output.content}
        </div>
      )}
    </div>
  );
}
