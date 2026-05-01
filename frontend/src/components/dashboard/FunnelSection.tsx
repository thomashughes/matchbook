/**
 * FunnelSection — Sankey of application stage flow on the dashboard.
 *
 * Reads /dashboard/funnel and renders a Recharts Sankey. Recharts is
 * already a dep (used elsewhere for the radar/bar charts), so we don't
 * pull in plotly just for one chart.
 *
 * Empty-state rule:
 *   The chart only reads cleanly with at least two transitions across
 *   at least two stages — anything less and the diagram is a single
 *   line that takes more space than it earns. We treat
 *   `links.length < 2` as the empty signal and show the prompt instead.
 *
 * Time-window toggle:
 *   "All / 90d / 365d" maps directly to the WindowKey on the backend.
 *   Recharts re-mounts the Sankey when its `data` prop identity
 *   changes, which is exactly what we want — animating between two
 *   wildly different topologies looks worse than a quick repaint.
 */
import { useMemo, useState } from 'react';
import { Sankey, Tooltip, ResponsiveContainer, Layer, Rectangle } from 'recharts';
import { useFunnel } from '@/api/hooks';
import type { FunnelWindow } from '@/types/models';

// Warm Modern palette stops — keyed by stage so the funnel reads the
// same colour story as StatusBadge. Hex literals because Recharts
// nodes accept inline `fill`, not Tailwind classes.
const NODE_COLOUR: Record<string, string> = {
  saved: '#c5b9a3',
  applied: '#c89b3c',
  first_interview: '#5d8bb8',
  second_interview: '#3a6995',
  final_interview: '#1f4670',
  offer: '#3a8a8a',
  accepted: '#2c6b6b',
  rejected: '#b25540',
  withdrawn: '#9a8c79',
  declined: '#8d7f6a',
  ghosted: '#a89c87',
};

const FALLBACK_COLOUR = '#a89c87';

const WINDOWS: { key: FunnelWindow; label: string }[] = [
  { key: 'all', label: 'All time' },
  { key: '90d', label: 'Last 90 days' },
  { key: '365d', label: 'Last 365 days' },
];

export function FunnelSection() {
  const [windowKey, setWindowKey] = useState<FunnelWindow>('all');
  const funnel = useFunnel(windowKey);

  // Recharts Sankey wants links keyed by integer index into the nodes
  // array. The API returns them keyed by stage id (more stable across
  // server changes), so we translate here. useMemo keeps the data
  // identity stable so Recharts doesn't redraw on every parent render.
  const chartData = useMemo(() => {
    if (!funnel.data) return null;
    const idToIdx = new Map<string, number>();
    funnel.data.nodes.forEach((n, i) => idToIdx.set(n.id, i));
    const links = funnel.data.links
      // Skip links whose endpoints aren't in the node set — shouldn't
      // happen, but a single orphan kills the whole render in Recharts.
      .filter((l) => idToIdx.has(l.source) && idToIdx.has(l.target))
      .map((l) => ({
        source: idToIdx.get(l.source)!,
        target: idToIdx.get(l.target)!,
        value: l.value,
      }));
    const nodes = funnel.data.nodes.map((n) => ({
      name: `${n.label} (${n.count})`,
      stage: n.id,
    }));
    return { nodes, links };
  }, [funnel.data]);

  return (
    <section className="mb-card">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div>
          <h2 className="mb-display text-lg">Application funnel</h2>
          <p className="text-xs text-ink-3 mt-0.5">
            How your applications have moved through the pipeline.
          </p>
        </div>
        <div className="flex gap-1 rounded-full bg-parchment p-1">
          {WINDOWS.map((w) => {
            const active = windowKey === w.key;
            return (
              <button
                key={w.key}
                onClick={() => setWindowKey(w.key)}
                className={`text-xs px-3 py-1 rounded-full transition ${
                  active ? 'bg-ink text-cream' : 'text-ink-2 hover:text-ink'
                }`}
              >
                {w.label}
              </button>
            );
          })}
        </div>
      </div>

      <FunnelBody loading={funnel.isLoading} error={!!funnel.error} data={chartData} />
    </section>
  );
}

function FunnelBody({
  loading,
  error,
  data,
}: {
  loading: boolean;
  error: boolean;
  data: { nodes: { name: string; stage: string }[]; links: { source: number; target: number; value: number }[] } | null;
}) {
  if (loading) {
    return <div className="text-sm text-ink-3 py-10 text-center">Loading funnel…</div>;
  }
  if (error || !data) {
    return (
      <div className="text-sm text-rust py-10 text-center">
        Couldn't load the funnel right now.
      </div>
    );
  }
  // Single-stage funnels (e.g. "everything is saved") have zero links
  // and would render as a void canvas. Two transitions is the minimum
  // for a Sankey to convey anything useful.
  if (data.links.length < 2) {
    return (
      <div className="text-sm text-ink-2 py-10 text-center leading-relaxed">
        Add more roles and update their status to see your funnel here.
      </div>
    );
  }

  return (
    <>
      {/* Desktop: Recharts Sankey. Needs horizontal room for labels +
          band geometry — only readable above the md breakpoint. */}
      <div className="hidden md:block h-[320px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <Sankey
            data={data}
            nodePadding={24}
            nodeWidth={14}
            margin={{ top: 8, right: 80, bottom: 8, left: 8 }}
            // Custom node so we can colour each rectangle by its stage —
            // Recharts default uses a single fill across every node.
            node={<FunnelNode />}
            // Default link is a thin grey ribbon; bump the colour and
            // opacity so it reads on the parchment background.
            link={{ stroke: '#9a8c79', strokeOpacity: 0.45 }}
          >
            <Tooltip
              formatter={(value: number) => [`${value} job${value === 1 ? '' : 's'}`, 'Flow']}
            />
          </Sankey>
        </ResponsiveContainer>
      </div>

      {/* Mobile: vertical funnel bars. Sankey's branching detail is lost
          by design — at phone width that detail is unreadable anyway and
          column counts dominate the signal. */}
      <div className="md:hidden">
        <MobileFunnel nodes={data.nodes} />
      </div>
    </>
  );
}

// Pipeline order for the mobile funnel. Active stages first (saved →
// offer/accepted), terminal/lost stages last so the eye reads "advance"
// at the top and "drop-off" at the bottom. Stages absent from this list
// fall to the end via indexOf returning -1.
const STAGE_ORDER = [
  'saved',
  'applied',
  'first_interview',
  'second_interview',
  'final_interview',
  'offer',
  'accepted',
  'rejected',
  'declined',
  'withdrawn',
  'ghosted',
];

function MobileFunnel({ nodes }: { nodes: { name: string; stage: string }[] }) {
  // The parent useMemo already formats `name` as "Label (count)". Parse
  // count back out rather than threading the raw value through — keeps
  // the desktop chartData shape unchanged.
  const parsed = nodes
    .map((n) => {
      const m = n.name.match(/\((\d+)\)$/);
      return {
        stage: n.stage,
        label: n.name.replace(/\s*\(\d+\)$/, ''),
        count: m ? Number(m[1]) : 0,
      };
    })
    .filter((n) => n.count > 0)
    .sort((a, b) => {
      const ai = STAGE_ORDER.indexOf(a.stage);
      const bi = STAGE_ORDER.indexOf(b.stage);
      // Unknown stages (-1) sink to the bottom but stay in API order
      // relative to each other.
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    });

  if (parsed.length === 0) {
    return (
      <div className="text-sm text-ink-2 py-10 text-center">
        Add more roles to see your funnel.
      </div>
    );
  }

  // Bar widths are relative to the busiest stage so the densest column
  // fills the row and the rest scale beneath it. Absolute counts shown
  // at the right keep the actual numbers honest.
  const max = Math.max(...parsed.map((n) => n.count));

  return (
    <div className="space-y-2 py-2">
      {parsed.map((n) => {
        const pct = (n.count / max) * 100;
        const colour = NODE_COLOUR[n.stage] ?? FALLBACK_COLOUR;
        return (
          <div key={n.stage} className="flex items-center gap-3">
            <div className="text-xs text-ink-2 w-[110px] shrink-0 truncate">{n.label}</div>
            <div className="flex-1 h-7 bg-parchment rounded overflow-hidden">
              <div
                className="h-full rounded transition-all"
                style={{ width: `${pct}%`, background: colour, opacity: 0.95 }}
              />
            </div>
            <div className="text-xs font-medium text-ink w-7 text-right shrink-0 tabular-nums">
              {n.count}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Recharts hands every node prop here. The shape includes x/y/width/
// height (already laid out) and the original payload (our `name` and
// `stage`). We render the rectangle plus a label outside to the right.
function FunnelNode(props: {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  index?: number;
  payload?: { name: string; stage: string };
  containerWidth?: number;
}) {
  const { x = 0, y = 0, width = 0, height = 0, payload, containerWidth = 0 } = props;
  const stage = payload?.stage ?? '';
  const colour = NODE_COLOUR[stage] ?? FALLBACK_COLOUR;
  // Anchor the label inside the chart for the rightmost-ish nodes so
  // it doesn't get clipped by the container edge.
  const labelOnRight = x + width + 100 < containerWidth;
  return (
    <Layer>
      <Rectangle x={x} y={y} width={width} height={height} fill={colour} fillOpacity={0.95} />
      <text
        x={labelOnRight ? x + width + 6 : x - 6}
        y={y + height / 2}
        textAnchor={labelOnRight ? 'start' : 'end'}
        dominantBaseline="middle"
        fontSize={11}
        fill="#3d3530"
      >
        {payload?.name ?? ''}
      </text>
    </Layer>
  );
}
