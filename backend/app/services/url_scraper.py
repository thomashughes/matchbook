"""
Fetch job description text from a URL.

Constraints and design notes:
    - LinkedIn URLs are rejected outright (§3.3): they actively block
      scraping and it's against their ToS. The browser extension covers
      LinkedIn in Phase 4.
    - We fetch via httpx with a browser-like User-Agent (some ATS
      platforms 403 headless requests) and a strict timeout to avoid
      hanging a worker on a slow site.
    - Content extraction: try structured ATS selectors first (Greenhouse,
      Lever, Workable), then fall back to a generic "largest <article>
      or <main>" heuristic.
    - Size cap on response body (1MB) prevents a hostile URL from
      streaming gigabytes into our memory.

This is intentionally NOT a robust general-purpose scraper. For sites
we don't recognise we produce a best-effort extraction, and the UI
offers "paste text" as the reliable fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException, status

UA = "Mozilla/5.0 (compatible; Matchbook/2.0; +https://matchbook.tag-art.co.uk/bot)"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_BYTES = 1_000_000

BLOCKED_HOSTS = {"linkedin.com", "www.linkedin.com"}


@dataclass
class ScrapedJob:
    title: str | None
    company: str | None
    description: str


def _extract_ats(soup: BeautifulSoup, host: str) -> ScrapedJob | None:
    """Try known ATS selectors. Returns None if the host is unknown.

    Each branch is scoped narrowly — a single bad selector on one ATS
    shouldn't affect others. Selectors checked against real postings
    as of early 2026; ATS platforms change their markup, so expect
    occasional breakage and fall through to generic extraction.
    """
    if "greenhouse.io" in host or "boards.greenhouse.io" in host:
        title = soup.select_one(".app-title, h1")
        company = soup.select_one(".company-name")
        body = soup.select_one("#content, .section-wrapper")
        if body:
            return ScrapedJob(
                title=title.get_text(strip=True) if title else None,
                company=company.get_text(strip=True) if company else None,
                description=body.get_text("\n", strip=True),
            )
    if "lever.co" in host:
        title = soup.select_one(".posting-headline h2, h2")
        body = soup.select_one(".section-wrapper.posting, .section-wrapper")
        if body:
            return ScrapedJob(
                title=title.get_text(strip=True) if title else None,
                company=None,  # Lever shows company elsewhere; leave None.
                description=body.get_text("\n", strip=True),
            )
    if "workable.com" in host:
        title = soup.select_one("h1, h2")
        body = soup.select_one('[data-ui="job-description"], main')
        if body:
            return ScrapedJob(
                title=title.get_text(strip=True) if title else None,
                company=None,
                description=body.get_text("\n", strip=True),
            )
    return None


def _extract_generic(soup: BeautifulSoup) -> ScrapedJob:
    """Fallback: pick the longest <article> / <main> / <section>."""
    title = soup.select_one("h1")
    # Remove nav / footer noise before measuring candidates.
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    candidates = soup.find_all(["article", "main", "section"])
    best = max(candidates, key=lambda e: len(e.get_text(strip=True)), default=soup.body or soup)
    return ScrapedJob(
        title=title.get_text(strip=True) if title else None,
        company=None,
        description=best.get_text("\n", strip=True),
    )


async def scrape_job_url(url: str) -> ScrapedJob:
    host = urlparse(url).hostname or ""
    if any(host.endswith(b) for b in BLOCKED_HOSTS):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="LinkedIn URLs are not supported. Use the browser extension or paste the text.",
        )

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": UA}) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            body = resp.content[:MAX_BYTES]
    except httpx.HTTPError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Could not fetch that URL: {e.__class__.__name__}",
        ) from e

    soup = BeautifulSoup(body, "html.parser")
    return _extract_ats(soup, host) or _extract_generic(soup)
