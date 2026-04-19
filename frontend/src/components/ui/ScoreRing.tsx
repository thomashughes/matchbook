/**
 * ScoreRing — SVG circular progress indicator for match scores.
 *
 * Colour: continuous red-amber-green scale via HSL. 0 → red (hue 0),
 * 50 → amber (hue 50), 100 → green (hue 130). Linear interpolation on
 * hue gives a smooth gradient that tracks the score precisely — a 78
 * reads visibly "better" than a 72, which the old three-bucket scheme
 * couldn't express. Saturation and lightness are fixed so the ring
 * sits comfortably on the cream background without washing out.
 *
 * Implemented in SVG (not a div + transform) so it scales crisply at
 * any size without blurring on retina, and so the stroke animation
 * feels smooth via stroke-dashoffset rather than width percentage.
 */

interface Props {
  score: number | null;
  size?: number;
  label?: string;
}

// Exported so other components (e.g. the dimension bars on the job
// detail page) can use the same colour scale for visual consistency.
export function scoreColour(score: number | null): string {
  if (score == null) return 'var(--ink-3)';
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const hue = Math.round(pct * 130); // 0=red, 130=green-ish
  return `hsl(${hue}, 65%, 42%)`;
}

export function ScoreRing({ score, size = 64, label }: Props) {
  const stroke = size / 10;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score ?? 0)) / 100;
  const offset = c * (1 - pct);

  const colour = scoreColour(score);

  return (
    <div className="inline-flex flex-col items-center" style={{ width: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none" stroke="var(--parchment)" strokeWidth={stroke}
        />
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none" stroke={colour} strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: 'stroke-dashoffset 600ms ease, stroke 600ms ease' }}
        />
        <text
          x="50%" y="50%" textAnchor="middle" dominantBaseline="central"
          fontFamily="Fraunces, serif"
          fontWeight={600}
          fontSize={size / 3}
          fill="var(--ink)"
        >
          {score == null ? '—' : score}
        </text>
      </svg>
      {label && <div className="mt-1 text-xs text-ink-3">{label}</div>}
    </div>
  );
}
