/**
 * OutreachPanel — AI-drafted outreach messages for a job.
 *
 * Mirrors the CoverLetterPanel pattern (segmented controls, version
 * history, per-version collapse/copy/delete) so the Job Detail page
 * reads as a consistent set of AI actions rather than bespoke widgets
 * per feature.
 *
 * Three knobs: channel (LinkedIn connection / InMail / email),
 * recipient role (hiring manager / recruiter / team member / referral),
 * and an optional recipient name. Role is more impactful than channel
 * for the output — it changes what evidence Claude leads with — which
 * is why it's exposed as a first-class control rather than buried in
 * free-text.
 */
import { useState } from 'react';
import { Check, ChevronDown, Copy, Loader2, Send, Trash2 } from 'lucide-react';
import {
  useAIOutputs,
  useDeleteAIOutput,
  useGenerateOutreach,
} from '@/api/hooks';
import type {
  JobAIOutput,
  OutreachChannel,
  OutreachRecipientRole,
} from '@/types/models';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';

const CHANNELS: { value: OutreachChannel; label: string }[] = [
  { value: 'email', label: 'Email' },
  { value: 'linkedin_inmail', label: 'InMail' },
  { value: 'linkedin_connection', label: 'Connection' },
];

const ROLES: { value: OutreachRecipientRole; label: string }[] = [
  { value: 'hiring_manager', label: 'Hiring manager' },
  { value: 'recruiter', label: 'Recruiter' },
  { value: 'team_member', label: 'Team member' },
  { value: 'referral', label: 'Referral' },
];

export function OutreachPanel({ jobId }: { jobId: string }) {
  const [channel, setChannel] = useState<OutreachChannel>('email');
  const [role, setRole] = useState<OutreachRecipientRole>('hiring_manager');
  const [recipientName, setRecipientName] = useState('');

  const list = useAIOutputs(jobId, 'outreach');
  const generate = useGenerateOutreach(jobId);
  const remove = useDeleteAIOutput(jobId, 'outreach');

  const messages = list.data ?? [];

  const count = messages.length;
  const hint = list.isLoading
    ? 'Loading…'
    : count === 0
      ? 'Not yet generated'
      : `${count} version${count === 1 ? '' : 's'}`;

  return (
    <CollapsibleSection title="Outreach" hint={hint}>
      <div className="flex flex-wrap gap-4 mb-4">
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

        <div>
          <div className="mb-label mb-1">Recipient</div>
          <div className="inline-flex rounded-full bg-parchment p-0.5">
            {ROLES.map((r) => (
              <button
                key={r.value}
                onClick={() => setRole(r.value)}
                className={`px-3 py-1 text-xs rounded-full transition ${
                  role === r.value ? 'bg-ink text-white' : 'text-ink-2'
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 min-w-[180px]">
          <div className="mb-label mb-1">Name (optional)</div>
          <input
            value={recipientName}
            onChange={(e) => setRecipientName(e.target.value)}
            placeholder="e.g. Priya Patel"
            className="mb-input py-1 text-sm"
          />
        </div>

        <div className="self-end">
          <button
            className="mb-btn-primary flex items-center gap-2"
            onClick={() =>
              generate.mutate({
                channel,
                recipient_role: role,
                recipient_name: recipientName.trim() || null,
              })
            }
            disabled={generate.isPending}
          >
            {generate.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
            {generate.isPending
              ? 'Drafting…'
              : messages.length === 0
                ? 'Draft message'
                : 'Draft another'}
          </button>
        </div>
      </div>

      {messages.length === 0 && !generate.isPending && (
        <p className="text-sm text-ink-3">
          Draft a tailored message to a hiring contact — each click saves
          a new version you can copy and edit before sending.
        </p>
      )}

      {messages.length > 0 && (
        <div className="space-y-3">
          {messages.map((m, i) => (
            <OutreachCard
              key={m.id}
              output={m}
              defaultOpen={i === 0}
              onDelete={() => remove.mutate(m.id)}
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

function OutreachCard({
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

  // Params are stored as Record<string, unknown>; coerce into readable
  // chips. Unknown values fall back to JSON so nothing's lost.
  const channelLabel =
    CHANNELS.find((c) => c.value === output.params.channel)?.label ??
    String(output.params.channel ?? '');
  const roleLabel =
    ROLES.find((r) => r.value === output.params.recipient_role)?.label ??
    String(output.params.recipient_role ?? '');
  const name = (output.params.recipient_name as string | null) || null;

  return (
    <div className="rounded-lg border border-border bg-cream/50 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between p-3 hover:bg-cream/80 transition"
      >
        <div className="flex items-center gap-2 text-xs text-ink-3">
          <ChevronDown
            size={14}
            className={`transition-transform ${open ? '' : '-rotate-90'}`}
          />
          <span className="font-medium text-ink-2">v{output.version}</span>
          <span>·</span>
          <span>{channelLabel}</span>
          <span>·</span>
          <span>{roleLabel}</span>
          {name && (
            <>
              <span>·</span>
              <span>{name}</span>
            </>
          )}
          <span>·</span>
          <span>{new Date(output.created_at).toLocaleString()}</span>
        </div>
        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={copy}
            className="p-1.5 rounded hover:bg-parchment text-ink-3 hover:text-ink"
            title="Copy"
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
