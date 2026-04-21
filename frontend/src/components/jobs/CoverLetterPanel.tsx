/**
 * CoverLetterPanel — AI-action block on the job detail page.
 *
 * Users pick a tone + length, hit generate, and Claude returns a
 * tailored letter that's persisted as the next version. Prior versions
 * stay listed so users can compare approaches ("formal/short" vs
 * "conversational/detailed") without losing the originals.
 *
 * Three reasons each UI bit is the way it is:
 *   - Tone + length as segmented buttons rather than selects: two
 *     small choice sets, segmented controls surface options without
 *     requiring a click to reveal them.
 *   - Latest letter rendered inline as read-only text inside a card,
 *     not a textarea. The mental model is "pastable output", not
 *     "editable draft" — editing happens in the user's actual
 *     destination (email/Workday).
 *   - Copy + delete are per-version. No bulk actions — cover letters
 *     are low-volume and deliberate.
 */
import { useState } from 'react';
import { Check, ChevronDown, Copy, Loader2, Sparkles, Trash2 } from 'lucide-react';
import {
  useCoverLetters,
  useDeleteCoverLetter,
  useGenerateCoverLetter,
  useProfile,
} from '@/api/hooks';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';
import { QuotaCaption } from './QuotaCaption';

type Tone = 'formal' | 'conversational';
type Length = 'short' | 'standard' | 'detailed';

const TONES: { value: Tone; label: string }[] = [
  { value: 'conversational', label: 'Conversational' },
  { value: 'formal', label: 'Formal' },
];

const LENGTHS: { value: Length; label: string }[] = [
  { value: 'short', label: 'Short' },
  { value: 'standard', label: 'Standard' },
  { value: 'detailed', label: 'Detailed' },
];

export function CoverLetterPanel({ jobId }: { jobId: string }) {
  const [tone, setTone] = useState<Tone>('conversational');
  const [length, setLength] = useState<Length>('standard');

  const list = useCoverLetters(jobId);
  const generate = useGenerateCoverLetter(jobId);
  const remove = useDeleteCoverLetter(jobId);
  // Profile version query — compared to each letter's snapshotted
  // profile_version to show a "previous profile" pill on old letters.
  const prof = useProfile();
  const currentProfileVersion = prof.data?.profile_version ?? 1;

  const letters = list.data ?? [];

  const count = letters.length;
  const hint = list.isLoading
    ? 'Loading…'
    : count === 0
      ? 'Not yet generated'
      : `${count} version${count === 1 ? '' : 's'}`;

  return (
    <CollapsibleSection title="Cover letter" hint={hint}>
      {/* Controls */}
      <div className="flex flex-wrap gap-4 mb-4">
        <div>
          <div className="mb-label mb-1">Tone</div>
          <div className="inline-flex rounded-full bg-parchment p-0.5">
            {TONES.map((t) => (
              <button
                key={t.value}
                onClick={() => setTone(t.value)}
                className={`px-3 py-1 text-xs rounded-full transition ${
                  tone === t.value ? 'bg-ink text-white' : 'text-ink-2'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="mb-label mb-1">Length</div>
          <div className="inline-flex rounded-full bg-parchment p-0.5">
            {LENGTHS.map((l) => (
              <button
                key={l.value}
                onClick={() => setLength(l.value)}
                className={`px-3 py-1 text-xs rounded-full transition ${
                  length === l.value ? 'bg-ink text-white' : 'text-ink-2'
                }`}
              >
                {l.label}
              </button>
            ))}
          </div>
        </div>

        <div className="ml-auto self-end">
          <button
            className="mb-btn-primary flex items-center gap-2"
            onClick={() => generate.mutate({ tone, length })}
            disabled={generate.isPending}
          >
            {generate.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Sparkles size={14} />
            )}
            {generate.isPending
              ? 'Writing…'
              : letters.length === 0
                ? 'Generate'
                : 'Generate another'}
          </button>
          <QuotaCaption jobId={jobId} resource="cover_letter" />
        </div>
      </div>

      {/* Empty state */}
      {letters.length === 0 && !generate.isPending && (
        <p className="text-sm text-ink-3">
          Generate a cover letter tailored to this role using your profile.
          Each click saves a new version.
        </p>
      )}

      {/* Version list */}
      {letters.length > 0 && (
        <div className="space-y-3">
          {letters.map((l, i) => (
            <LetterCard
              key={l.id}
              letter={l}
              defaultOpen={i === 0}
              stale={l.profile_version !== currentProfileVersion}
              onDelete={() => remove.mutate(l.id)}
            />
          ))}
        </div>
      )}

      {/* Surface any generation error inline so failed calls don't go
          silent. The standard case is a 429 from the rate limiter. */}
      {generate.isError && (
        <p className="text-sm text-rust mt-3">
          Couldn't generate — please try again in a moment.
        </p>
      )}
    </CollapsibleSection>
  );
}

function LetterCard({
  letter,
  defaultOpen,
  stale,
  onDelete,
}: {
  letter: import('@/types/models').CoverLetter;
  defaultOpen: boolean;
  stale: boolean;
  onDelete: () => void;
}) {
  // Only the latest version auto-expands. Older versions start collapsed
  // so a long history doesn't swamp the page — the whole point of the
  // version list is browsing, not reading everything at once.
  const [open, setOpen] = useState(defaultOpen);
  const [copied, setCopied] = useState(false);

  async function copy(e: React.MouseEvent) {
    e.stopPropagation();
    await navigator.clipboard.writeText(letter.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="rounded-lg border border-border bg-cream/50 overflow-hidden">
      {/* Header doubles as the toggle so the whole strip is clickable —
          easier target than a small chevron. */}
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
          <span className="font-medium text-ink-2">v{letter.version}</span>
          <span>·</span>
          <span className="capitalize">{letter.tone}</span>
          <span>·</span>
          <span className="capitalize">{letter.length}</span>
          <span>·</span>
          <span>{new Date(letter.created_at).toLocaleString()}</span>
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
          {letter.content}
        </div>
      )}
    </div>
  );
}
