"""Pydantic schemas for the dashboard endpoints (Sankey funnel for now).

The shape mirrors what react-plotly.js's Sankey trace consumes after a
small client-side transform: a flat array of nodes and a flat array of
links keyed by node id. We deliberately don't ship the Plotly-native
{label, source, target} integer-indexed shape from the server because
that bakes the rendering library's contract into the API. If we ever
swap Plotly for nivo or a custom SVG, only the frontend changes.
"""

from datetime import datetime

from pydantic import BaseModel


class FunnelNode(BaseModel):
    """One stage in the funnel.

    `id` is the canonical status string (e.g. "first_interview").
    `label` is the human-friendly form ("First interview").
    `count` is how many jobs ever entered this stage in the window.
    """

    id: str
    label: str
    count: int


class FunnelLink(BaseModel):
    """One transition between two stages.

    `value` is the number of jobs that moved from `source` to `target`
    in the window. Self-loops (status patched to its current value)
    never appear because the API filters them out at write time.
    """

    source: str
    target: str
    value: int


class FunnelOut(BaseModel):
    nodes: list[FunnelNode]
    links: list[FunnelLink]
    # Total distinct jobs represented in the funnel data. Useful so the
    # frontend can render an empty-state message ("Add more roles to
    # see your funnel") without doing its own arithmetic on links.
    total_jobs: int
    window_start: datetime | None
    window_end: datetime
