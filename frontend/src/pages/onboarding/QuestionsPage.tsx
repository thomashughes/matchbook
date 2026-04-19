/**
 * QuestionsPage — step 2 of onboarding.
 *
 * Claude generated up to 10 clarifying questions after reading the CV.
 * We present them one at a time (conversational, not a form) so the
 * user never sees a wall of fields. Answers accumulate locally, then
 * submit as a single batch to /profile/answers which triggers the
 * final profile-generation Claude call.
 */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useClarifyingQuestions, useSubmitAnswers } from '@/api/hooks';
import { AILoadingSteps } from '@/components/ui/AILoadingSteps';

const GEN_STEPS = [
  'Pulling together your answers…',
  'Building your profile…',
  'Setting your preferences…',
];

export function QuestionsPage() {
  const nav = useNavigate();
  const q = useClarifyingQuestions(true);
  const submit = useSubmitAnswers();
  const [i, setI] = useState(0);
  // Keyed by question id locally for easy edits/back-navigation, but
  // the submit payload maps each entry back to its question text +
  // kind — that's what the backend AnswerIn schema expects.
  // Keyed by question id locally for easy edits/back-navigation, but
  // the submit payload maps each entry back to its question text +
  // kind — that's what the backend AnswerIn schema expects.
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState('');
  // Free-form final note. Optional — user can leave it blank. Attached
  // to the submission as a synthetic "anything_else" answer so the
  // profile generator gets to see it.
  const [extra, setExtra] = useState('');

  const questions = q.data?.questions ?? [];
  const current = questions[i];
  const done = i >= questions.length;

  const progress = useMemo(
    () => (questions.length === 0 ? 0 : Math.round((i / questions.length) * 100)),
    [i, questions.length],
  );

  function next() {
    if (!current || !draft.trim()) return;
    const updated = { ...answers, [current.id]: draft.trim() };
    setAnswers(updated);
    setDraft('');
    setI((n) => n + 1);
  }

  async function finish() {
    // Map id-keyed answers back to the backend's text+kind shape.
    const payload = Object.entries(answers)
      .map(([qid, answer]) => {
        const qmeta = questions.find((qq) => qq.id === qid);
        if (!qmeta) return null;
        return { question: qmeta.text, answer, kind: qmeta.kind };
      })
      .filter(Boolean) as { question: string; answer: string; kind: string }[];
    // Append the optional "anything else" note as a free-text answer
    // so the profile generator sees it alongside the structured ones.
    if (extra.trim()) {
      payload.push({
        question: 'Is there anything else you\'d like to add?',
        answer: extra.trim(),
        kind: 'free_text',
      });
    }
    await submit.mutateAsync(payload);
    nav('/onboarding/done');
  }

  if (q.isLoading) {
    return (
      <div className="min-h-full bg-cream flex items-center justify-center p-6">
        <div className="mb-card w-full max-w-xl">
          <AILoadingSteps steps={['Reading your CV…', 'Thinking of good questions…']} />
        </div>
      </div>
    );
  }

  if (submit.isPending) {
    return (
      <div className="min-h-full bg-cream flex items-center justify-center p-6">
        <div className="mb-card w-full max-w-xl">
          <AILoadingSteps steps={GEN_STEPS} />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-full bg-cream flex items-center justify-center p-6">
      <div className="mb-card w-full max-w-xl">
        <div className="h-1 bg-parchment rounded-full mb-5 overflow-hidden">
          <div
            className="h-full bg-teal transition-all"
            style={{ width: `${done ? 100 : progress}%` }}
          />
        </div>

        {done ? (
          <>
            <div className="mb-display text-xl mb-2">Almost done.</div>
            <p className="text-sm text-ink-2 mb-4">
              Anything else you'd like us to know before we build your profile?
              Skip it if not — this is optional.
            </p>
            <textarea
              value={extra}
              onChange={(e) => setExtra(e.target.value)}
              className="mb-input min-h-[100px] mb-4"
              placeholder="Anything else — career pivots, red lines, nice-to-haves…"
            />
            <p className="text-sm text-ink-2 mb-5">
              We'll build your profile from your CV and your answers — takes about ten seconds.
            </p>
            <div className="flex justify-end">
              {/* Disable while the mutation is in flight so double-clicks
                  can't enqueue duplicate generation calls, and show a
                  spinner inline so the click registers immediately even
                  before the loading view takes over. */}
              <button
                className="mb-btn-primary flex items-center gap-2"
                onClick={finish}
                disabled={submit.isPending}
              >
                {submit.isPending && (
                  <span className="inline-block w-3.5 h-3.5 border-2 border-cream/60 border-t-cream rounded-full animate-spin" />
                )}
                {submit.isPending ? 'Building…' : 'Build my profile'}
              </button>
            </div>
          </>
        ) : current ? (
          <>
            <div className="text-xs uppercase tracking-wider text-ink-3 mb-2">
              Question {i + 1} of {questions.length}
            </div>
            <div className="mb-display text-xl mb-4">{current.text}</div>
            <textarea
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) next();
              }}
              className="mb-input min-h-[120px]"
              placeholder="Type your answer…"
            />
            <p className="mt-2 text-xs text-ink-3">⌘/Ctrl + Enter to continue</p>

            <div className="flex justify-between mt-4">
              <button
                className="mb-btn-ghost"
                onClick={() => setI((n) => Math.max(0, n - 1))}
                disabled={i === 0}
              >
                Back
              </button>
              <button className="mb-btn-primary" onClick={next} disabled={!draft.trim()}>
                Next
              </button>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
