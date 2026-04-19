/**
 * ScoreRadar — six-dimension radar chart for job detail + compare views.
 *
 * Uses Recharts because the handoff specifies it (§3.5). The dimension
 * order is fixed so stacked/compared charts read consistently.
 */
import {
  PolarAngleAxis, PolarGrid, PolarRadiusAxis,
  Radar, RadarChart, ResponsiveContainer,
} from 'recharts';
import type { JobScore } from '@/types/models';

const DIMS: { key: keyof JobScore; label: string }[] = [
  { key: 'skills_score',     label: 'Skills' },
  { key: 'experience_score', label: 'Experience' },
  { key: 'salary_score',     label: 'Salary' },
  { key: 'location_score',   label: 'Location' },
  { key: 'culture_score',    label: 'Culture' },
  { key: 'trajectory_score', label: 'Trajectory' },
];

export function ScoreRadar({ score, height = 300 }: { score: JobScore; height?: number }) {
  const data = DIMS.map((d) => ({ dimension: d.label, value: score[d.key] as number }));

  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <RadarChart data={data} outerRadius="75%">
          <PolarGrid stroke="var(--border)" />
          <PolarAngleAxis
            dataKey="dimension"
            tick={{ fill: 'var(--ink-2)', fontSize: 12 }}
          />
          <PolarRadiusAxis
            domain={[0, 100]}
            tick={{ fill: 'var(--ink-3)', fontSize: 10 }}
            axisLine={false}
          />
          <Radar
            dataKey="value"
            stroke="var(--teal)"
            fill="var(--teal)"
            fillOpacity={0.25}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
