/**
 * AILoadingSteps — one-at-a-time fading status messages for Claude ops.
 *
 * Why this shape: §7.4 "AI transparency" says never a blank spinner,
 * but a full checklist on screen is noisy and makes a 10s wait feel
 * like a form. We show a single line at a time, crossfade to the next,
 * and loop until the parent unmounts us on mutation success. This
 * reads as "something is happening right now" rather than "here is a
 * to-do list the computer is working through".
 *
 * Implementation notes:
 * - `phase` drives opacity/translate so the exit of step N and entry
 *   of step N+1 overlap — CSS transitions handle the tween, no
 *   animation library needed.
 * - Total cycle: 2.4s visible + ~0.4s crossfade. Tuned so each line is
 *   long enough to read comfortably (≈3s dwell including fade).
 */
import { useEffect, useState } from 'react';
import { Sparkles } from 'lucide-react';

const DWELL_MS = 2400; // visible before fade-out begins
const FADE_MS = 400;   // crossfade duration

export function AILoadingSteps({ steps }: { steps: string[] }) {
  const [idx, setIdx] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (steps.length === 0) return;
    let cancelled = false;
    // Two-stage cycle: fade out the current line, swap, fade the next in.
    const tick = () => {
      if (cancelled) return;
      setVisible(false);
      setTimeout(() => {
        if (cancelled) return;
        setIdx((i) => (i + 1) % steps.length);
        setVisible(true);
      }, FADE_MS);
    };
    const t = setInterval(tick, DWELL_MS + FADE_MS);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [steps.length]);

  if (steps.length === 0) return null;

  return (
    <div className="flex items-center justify-center gap-3 py-4 min-h-[48px]">
      {/* Sparkles pulses continuously so the line feels "alive" even
          mid-fade when the text is invisible. */}
      <Sparkles
        size={18}
        className="text-teal animate-pulse shrink-0"
        aria-hidden
      />
      <span
        key={idx}
        className="text-sm text-ink-2 transition-all ease-out"
        style={{
          opacity: visible ? 1 : 0,
          transform: visible ? 'translateY(0)' : 'translateY(4px)',
          transitionDuration: `${FADE_MS}ms`,
        }}
        aria-live="polite"
      >
        {steps[idx]}
      </span>
    </div>
  );
}
