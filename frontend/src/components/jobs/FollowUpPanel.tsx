/**
 * FollowUpPanel — AI-drafted follow-up messages tied to a stage in the
 * hiring process (post-application check-in, post-interview thank-you,
 * post-recruiter-call confirmation, silent-period nudge).
 *
 * Mirrors OutreachPanel's layout: two segmented selects (stage, channel)
 * plus one optional free-text input (context), Generate on the right,
 * version cards below. Stage is a bigger control surface than channel
 * because stage drives the message's entire shape (thank-you vs chase
 * vs check-in), while channel is a smaller formatting toggle.
 *
 * The `context` textarea is deliberately smaller than FormResponse's —
 * in a follow-up the context is *supporting* ("the ownership model Sara
 * described"), not the primary input; in a form-response the question
 * IS the primary input. Size signals weight.
 */
import { useState } from 'react';
import { Check, ChevronDown, Copy, Loader2, Send, Trash2 } from 'lucide-react';
import {
  useAIOutputs,
  useDeleteAIOutput,
  useGenerateFollowUp,
} from '@/api/hooks';
import type {
  FollowUpChannel,
  FollowUpStage,
  JobAIOutput,
} from '@/types/models';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';
import { useJobQuota } from '@/api/quota';
import { QuotaCaption } from './QuotaCaption';

const STAGES: { value: FollowUpStage; label: string }[] = [
  { value: 'post_application', label: 'After applying' },
  { value: 'post_interview', label: 'After interview' },
  { value: 'post_recruiter_call', label: 'After recruiter call' },
  { value: 'no_response', label: 'No response' },
];

const CHANNELS: { value: FollowUpChannel; label: string }[] = [
  { value: 'email', label: 'Email' },
  { value: 'linkedin', label: 'LinkedIn' },
];

export function FollowUpPanel({ jobId }: { jobId: string }) {
  const [stage, setStage] = useState<FollowUpStage>('post_application');
  const [channel, setChannel] = useState<FollowUpChannel>('email');
  const [context, setContext] = useState('');

  const list = useAIOutputs(jobId, 'follow_up');
  const generate = useGenerateFollowUp(jobId);
  const remove = useDeleteAIOutput(jobId, 'follow_up');
  const quota = useJobQuota(jobId, 'draft_follow_up');

  const messages = list.data ?? [];

  const count = messages.length;
  const hint = list.isLoading
    ? 'Loading…'
    : count === 0
      ? 'Not yet generated'
      : `${count} version${count === 1 ? '' : 's'}`;

  function submit() {
    // Trim before sending so an all-whitespace textarea doesn't pass
    // Pydantic's truthy check and show up as meaningless stored
    // context on the version card later.
    const trimmed = context.trim();
    generate.mutate({
      stage,
      channel,
      context: trimmed.length > 0 ? trimmed : null,
    });
  }

  return (
    <CollapsibleSection title="Follow-up" hint={hint}>
      <div className="flex flex-wrap gap-4 mb-4">
        <div>
          <div className="mb-label mb-1">Stage</div>
          <div className="inline-flex rounded-full bg-parchment p-0.5 flex-wrap">
            {STAGES.map((s) => (
              <button
                key={s.value}
                onClick={() => setStage(s.value)}
                className={`px-3 py-1 text-xs rounded-full transition ${
                  stage === s.value ? 'bg-ink text-white' : 'text-ink-2'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="mb-label mb-1">Channel</div>
          <div className="inline-flex rounded-full bg-parchment p-0.5">
            {CHANNELS.map((c) => (
              <button
                key={c.value}
                onClick={() => setChannel(c.value)}
                className={`px-3 py-1 text-xs rounded-full transition ${
                  channel === c.value ? 'bg-ink text-white' : 'text-ink-2'
                }`}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>

        <div className="self-end ml-auto">
          <button
            className="mb-btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={submit}
            disabled={generate.isPending || quota.atLimit}
            title={quota.atLimit ? 'No follow-up drafts left this month — upgrade for unlimited' : undefined}
          >
            {generate.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
            {generate.isPending
              ? 'Drafting…'
              : messages.length === 0
                ? 'Draft follow-up'
                : 'Draft another'}
          </button>
          <QuotaCaption jobId={jobId} resource="draft_follow_up" />
        </div>
      </div>

      {/* Context is below the segmented row because it's optional and
          secondary — putting it beside the chips would visually compete
          with the stage choice, which is the more important knob. */}
      <div className="mb-4">
        <div className="mb-label mb-1">
          Specific callback (optional)
        </div>
        <textarea
          value={context}
          onChange={(e) => setContext(e.target.value)}
          placeholder="Anything specific to reference — e.g. 'the ownership model Sara described', 'the £65k ideal we discussed', 'thanks for the book recommendation'."
          className="mb-input min-h-[64px] text-sm leading-relaxed"
          aria-label="Specific callback"
          maxLength={500}
        />
      </div>

      {messages.length === 0 && !generate.isPending && (
        <p className="text-sm text-ink-3">
          Draft a follow-up tuned to where you are in the process — a
          post-interview thank-you reads nothing like a silent-period
          nudge. Each click saves a new version.
        </p>
      )}

      {messages.length > 0 && (
        <div className="space-y-3">
          {messages.map((m, i) => (
            <FollowUpCard
              key={m.id}
              output={m}
              defaultOpen={i === 0}
              onDelete={() => {
                if (confirm('Delete this follow-up? This cannot be undone.')) {
                  remove.mutate(m.id);
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

function FollowUpCard({
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

  // Defensive coercion: params is Record<string, unknown> at the type
  // level because JSONB can hold anything. Unknown stages/channels fall
  // back to raw JSON so legacy rows don't render blank chips.
  const stageLabel =
    STAGES.find((s) => s.value === output.params.stage)?.label ??
    String(output.params.stage ?? '');
  const channelLabel =
    CHANNELS.find((c) => c.value === output.params.channel)?.label ??
    String(output.params.channel ?? '');
  const hasContext =
    typeof output.params.context === 'string' &&
    (output.params.context as string).trim().length > 0;

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
          <span className="shrink-0">{stageLabel}</span>
          <span className="shrink-0">·</span>
          <span className="shrink-0">{channelLabel}</span>
          {hasContext && (
            <>
              <span className="shrink-0">·</span>
              <span
                className="shrink-0 italic"
                title={output.params.context as string}
              >
                with callback
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
            aria-label="Copy follow-up"
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
            aria-label="Delete follow-up"
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
