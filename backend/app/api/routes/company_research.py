"""
Company research routes.

Distinct from the other AI actions in two ways:

1. Shared cache. The same company produces the same research regardless
   of which user asks — facts don't vary per user. So the cache table
   is NOT tenant-scoped, and the first user to research a company pays
   the Claude/web-search cost while every subsequent user hits instantly.
   Only the ownership check on the originating JOB is tenant-scoped.

2. Split GET/POST. GET is a pure cache read (404 on miss) so routine
   page visits never silently trigger a paid web_search run. POST
   explicitly generates (or refreshes) and writes the cache — that's
   the action the user takes when they actually want the data. Side
   effects live on the verb that implies them.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_verified_user, rate_limit_ai
from app.core.database import get_db
from app.models.company_research import CompanyResearchCache
from app.models.job import Job
from app.models.user import User
from app.prompts import company_research as research_prompt
from app.schemas.company_research import CompanyResearchOut
from app.services.ai_service import complete_text_with_web_search

router = APIRouter(prefix="/jobs/{job_id}/company-research", tags=["company-research"])


# How long a freshly-generated briefing stays valid. 7 days is long
# enough that a single user running a handful of company researches per
# week mostly gets cache hits, and short enough that quarterly news
# (funding rounds, leadership changes) gets picked up within a sprint.
# Expired rows are still returned on GET (with expires_at in the past)
# so the user sees their previous research instantly and can decide
# whether to refresh.
CACHE_TTL = timedelta(days=7)


# The JD is only used as a *bias hint* so Claude focuses the search on
# the hiring team's product area in multi-product companies. A full raw
# JD can be 5–10k chars (~2–3k input tokens) and every one of those
# tokens is billed on every research call. 1500 chars is enough to
# convey role + team signal without paying for boilerplate EEO/benefits
# sections.
JD_CONTEXT_MAX_CHARS = 1500


def _norm(name: str) -> str:
    """Normalise a company name for cache lookup.

    Lowercase + collapse whitespace. We deliberately don't strip
    punctuation ('& Co', '.com', 'Ltd') because those disambiguate
    real companies — 'Apple' vs 'Apple Inc' vs 'Apple.com' may or may
    not be the same company; the user's stored job.company is the
    source of truth for what they meant.
    """
    return " ".join(name.strip().lower().split())


async def _own_job(job_id: UUID, user: User, db: AsyncSession) -> Job:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


def _resolve_company(job: Job) -> str:
    """Return the job's company, raising 400 if it's missing/placeholder.

    'Unknown company' is the fallback written when JD parsing can't
    extract one — researching that string is pointless and would pollute
    the shared cache with a row that's useless to everyone.
    """
    company = (job.company or "").strip()
    if not company or company.casefold() in {"unknown company", "unknown"}:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                "This job doesn't have a company name. Edit the job to "
                "add one before researching."
            ),
        )
    return company


def _to_out(row: CompanyResearchCache, *, fresh: bool) -> CompanyResearchOut:
    # research_data is JSONB — we wrote it as
    # {"briefing": str, "sources": list[str]} on generation. Read
    # defensively so schema evolution doesn't blow up old rows.
    data = row.research_data or {}
    return CompanyResearchOut(
        company_name=row.company_name,
        briefing=str(data.get("briefing", "")),
        sources=list(data.get("sources", []) or []),
        cached_at=row.cached_at,
        expires_at=row.expires_at,
        fresh=fresh,
    )


@router.get(
    "",
    response_model=CompanyResearchOut,
    responses={404: {"description": "No cached research for this company."}},
)
async def get_company_research(
    job_id: UUID,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> CompanyResearchOut:
    """Read-only: return the cached briefing for the job's company.

    Expired rows are still returned (with expires_at in the past) so the
    UI can show stale results immediately alongside a refresh prompt,
    rather than forcing the user to wait for regeneration just to see
    something they already paid for. 404 means 'never researched'.
    """
    job = await _own_job(job_id, user, db)
    company = _resolve_company(job)
    normalized = _norm(company)

    result = await db.execute(
        select(CompanyResearchCache).where(
            CompanyResearchCache.company_name == normalized
        )
    )
    cached = result.scalar_one_or_none()
    if cached is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Company not researched yet.",
        )
    return _to_out(cached, fresh=False)


@router.post(
    "",
    response_model=CompanyResearchOut,
    status_code=status.HTTP_200_OK,
    # rate_limit_ai applies because POST always spends on web_search —
    # this is the only path that incurs cost. GET is free.
    dependencies=[Depends(rate_limit_ai)],
)
async def generate_company_research(
    job_id: UUID,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> CompanyResearchOut:
    """Generate (or regenerate) a briefing via Claude + web search.

    Writes to the shared cache, upserting on normalised company_name.
    Always runs — POST is the 'I explicitly want this' verb. Clients
    that just want to read cached data should use GET.
    """
    job = await _own_job(job_id, user, db)
    company = _resolve_company(job)
    normalized = _norm(company)
    now = datetime.now(timezone.utc)

    # Trim the JD before passing it as context. Full raw JDs can carry
    # thousands of tokens of boilerplate (benefits, EEO, legal) that add
    # nothing to the research bias and everything to the bill. Role +
    # team signal typically sits in the first ~1500 chars.
    jd_context = (job.description_raw or "")[:JD_CONTEXT_MAX_CHARS] or None

    briefing, sources = await complete_text_with_web_search(
        system=research_prompt.SYSTEM,
        user=research_prompt.build_user_message(
            company=company,
            job_description=jd_context,
        ),
        # 4096 comfortably holds a thorough multi-section briefing plus
        # source URLs; caps runaway output if Claude tries to summarise
        # every search hit.
        max_tokens=4096,
        # 2 focused searches covers overview + news/culture for most
        # companies. Each additional search pulls another full page of
        # raw HTML into the next model turn as input tokens — this is
        # the dominant cost of the whole call, so halving searches
        # roughly halves the bill. Bumping back to 3 is reasonable if
        # quality suffers on obscure companies.
        max_searches=2,
    )

    # Belt-and-braces: despite the "no preamble" instruction, Claude
    # sometimes narrates progress in the final text block ("Based on my
    # searches, I now have enough information…") before emitting the
    # OVERVIEW header. Drop everything before the first OVERVIEW line so
    # the cached briefing starts cleanly. If OVERVIEW isn't present at
    # all (sparse-data fallback), leave the text untouched.
    overview_match = re.search(r"^OVERVIEW\s*$", briefing, re.MULTILINE)
    if overview_match:
        briefing = briefing[overview_match.start() :].rstrip()

    expires_at = now + CACHE_TTL
    research_data = {"briefing": briefing, "sources": sources}

    # Upsert on company_name (unique index). ON CONFLICT lets us avoid a
    # select-then-update round trip and handles the race where two users
    # refresh the same company simultaneously — last writer wins, both
    # get fresh data on their respective responses.
    stmt = (
        pg_insert(CompanyResearchCache)
        .values(
            company_name=normalized,
            research_data=research_data,
            cached_at=now,
            expires_at=expires_at,
        )
        .on_conflict_do_update(
            index_elements=[CompanyResearchCache.company_name],
            set_={
                "research_data": research_data,
                "cached_at": now,
                "expires_at": expires_at,
            },
        )
        .returning(CompanyResearchCache)
    )
    result = await db.execute(stmt)
    row = result.scalar_one()
    await db.commit()

    return _to_out(row, fresh=True)
