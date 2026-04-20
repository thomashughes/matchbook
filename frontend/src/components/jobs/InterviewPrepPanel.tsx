/**
 * InterviewPrepPanel — AI-generated interview preparation sheet.
 *
 * Unlike the other AI actions in this panel family, interview prep is
 * NOT a message the user sends. It's a study aid — a single document
 * with three sections (Technical, Behavioural, Questions to ask). So
 * the panel reads similarly (segmented round selector + Generate +
 * versioned cards) but the generated content is longer and structured
 * rather than a single paragraph.
 *
 * Round is the primary knob because it shifts the whole mix — a phone
 * screen weights motivation/fit, a technical round front-loads deep
 * questions. `focus` is an optional topic bias.
 *
 * Rendering: Claude is instructed to output ALL-CAPS section headers
 * underlined with em-dashes, so the result renders cleanly inside a
 * `whitespace-pre-wrap` block without a markdown dependency. If richer
 * rendering becomes worth the weight later, swap the content block for
 * a markdown component — nothing else changes.
 */
import { useState } from 'react';
import {
  BookOpen,
  Check,
  ChevronDown,
  Copy,
  Loader2,
  Trash2,
} from 'lucide-react';
import {
  useAIOutputs,
  useDeleteAIOutput,
  useGenerateInterviewPrep,
} from '@/api/hooks';
import type { InterviewPrepRound, JobAIOutput } from '@/types/models';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';
import { QuotaCaption } from './QuotaCaption';

const ROUNDS: { value: InterviewPrepRound; label: string }[] = [
  { value: 'phone_screen', label: 'Phone screen' },
  { value: 'technical', label: 'Technical' },
  { value: 'behavioural', label: 'Behavioural' },
  { value: 'final', label: 'Final' },
  { value: 'general', label: 'General' },
];

export function InterviewPrepPanel({ jobId }: { jobId: string }) {
  const [round, setRound] = useState<InterviewPrepRound>('general');
  const [focus, setFocus] = useState('');

  const list = useAIOutputs(jobId, 'interview_prep');
  const generate = useGenerateInterviewPrep(jobId);
  const remove = useDeleteAIOutput(jobId, 'interview_prep');

  const sheets = list.data ?? [];

  const count = sheets.length;
  const hint = list.isLoading
    ? 'Loading…'
    : count === 0
      ? 'Not yet generated'
      : `${count} version${count === 1 ? '' : 's'}`;

  function submit() {
    const trimmed = focus.trim();
    generate.mutate({
      round,
      focus: trimmed.length > 0 ? trimmed : null,
    });
  }

  return (
    <CollapsibleSection title="Interview prep" hint={hint}>
      <div className="flex flex-wrap gap-4 mb-3">
        <div>
          <div className="mb-label mb-1">Round</div>
          <div className="inline-flex rounded-full bg-parchment p-0.5 flex-wrap">
            {ROUNDS.map((r) => (
              <button
                key={r.value}
                onClick={() => setRound(r.value)}
                className={`px-3 py-1 text-xs rounded-full transition ${
                  round === r.value ? 'bg-ink text-white' : 'text-ink-2'
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div className="self-end ml-auto">
          <button
            className="mb-btn-primary flex items-center gap-2"
            onClick={submit}
            disabled={generate.isPending}
          >
            {generate.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <BookOpen size={14} />
            )}
            {generate.isPending
              ? 'Preparing…'
              : sheets.length === 0
                ? 'Generate prep sheet'
                : 'Generate another'}
          </button>
          <QuotaCaption jobId={jobId} resource="draft_interview_prep" />
        </div>
      </div>

      {/* Focus sits below because it's optional and narrower in effect
          than the round selector — it biases question selection, it
          doesn't redefine the sheet. */}
      <div className="mb-4">
        <div className="mb-label mb-1">Focus (optional)</div>
        <input
          type="text"
          value={focus}
          onChange={(e) => setFocus(e.target.value)}
          placeholder="e.g. system design, React hooks, team leadership"
          className="mb-input py-1 text-sm"
          aria-label="Topic focus"
          maxLength={200}
        />
      </div>

      {sheets.length === 0 && !generate.isPending && (
        <p className="text-sm text-ink-3">
          Generate a prep sheet tailored to the upcoming round and this
          role — likely technical and behavioural questions, plus
          thoughtful questions for you to ask the interviewer. Each
          click saves a new version.
        </p>
      )}

      {sheets.length > 0 && (
        <div className="space-y-3">
          {sheets.map((s, i) => (
            <PrepCard
              key={s.id}
              output={s}
              defaultOpen={i === 0}
              onDelete={() => {
                if (
                  confirm('Delete this prep sheet? This cannot be undone.')
                ) {
                  remove.mutate(s.id);
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

function PrepCard({
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

  const roundLabel =
    ROUNDS.find((r) => r.value === output.params.round)?.label ??
    String(output.params.round ?? '');
  const focusVal =
    typeof output.params.focus === 'string'
      ? (output.params.focus as string).trim()
      : '';

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
          <span className="shrink-0">{roundLabel}</span>
          {focusVal && (
            <>
              <span className="shrink-0">·</span>
              <span className="italic truncate" title={focusVal}>
                {focusVal}
              </span>
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
            aria-label="Copy prep sheet"
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
            aria-label="Delete prep sheet"
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
