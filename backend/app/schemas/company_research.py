"""
Pydantic schemas for company research.

The research briefing is a single long-form text blob + a list of source
URLs that Claude cited during its web_search run. It's persisted in the
cache table verbatim (keyed by normalised company name) and returned
directly to the client — the frontend renders the text in a pre-wrap
block and the URLs as a clickable source list.

There's no Generate input schema: the only knob is the company name,
which comes from the job row, and an optional force-refresh flag on the
query string. Keeping the request body empty lets the endpoint be a GET
(cache-hit case) that also performs a write (cache-miss case) — a minor
REST bending we accept because it keeps the frontend one-call simple.
"""

from datetime import datetime

from pydantic import BaseModel


class CompanyResearchOut(BaseModel):
    company_name: str
    # Full briefing text, formatted with ALL-CAPS section headers
    # underlined by em-dashes. Frontend renders as whitespace-pre-wrap.
    briefing: str
    # URLs Claude cited or visited via web_search, deduplicated, in the
    # order encountered. Empty list is valid — small / stealth companies
    # may not surface anything.
    sources: list[str]
    # When this row was generated. The UI shows this so the user knows
    # how fresh the briefing is and can decide whether to force-refresh.
    cached_at: datetime
    # When this row goes stale. After this timestamp, the next non-
    # forced GET triggers a re-research.
    expires_at: datetime
    # True if the row was just generated (or refreshed) on this request,
    # False if served from cache. UI uses this to show a "freshly
    # generated" indicator vs "cached".
    fresh: bool
