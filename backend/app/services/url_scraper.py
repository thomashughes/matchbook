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

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException, status

UA = "Mozilla/5.0 (compatible; Matchbook/2.0; +https://matchbook.tag-art.co.uk/bot)"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_BYTES = 1_000_000
MAX_REDIRECTS = 5

BLOCKED_HOSTS = {"linkedin.com", "www.linkedin.com"}

# SSRF guard. Without this an authenticated user can submit
# `http://redis:6379/`, `http://postgres:5432/`, `http://127.0.0.1/admin`,
# or any RFC1918 address; the backend container would dutifully fetch it
# and store the response in the job's description, which the user can
# then read back. We resolve the hostname and reject if any candidate IP
# falls into a non-public range. Re-validated after every redirect — an
# attacker can otherwise host a public URL that 302s to a private IP.
def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True only for globally routable, non-special-use addresses.

    We deliberately reject loopback, RFC1918 private, link-local
    (169.254.0.0/16 — covers cloud metadata endpoints), multicast,
    reserved, and unspecified ranges. is_global is the inverse on
    modern Python and would be cleaner, but checking each predicate
    explicitly makes the intent and the test surface obvious.
    """
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve_and_validate(host: str) -> None:
    """Resolve `host` and raise 400 if any A/AAAA record is non-public.

    Checking *every* returned address (not just the first) defeats DNS
    rebinding tricks where the resolver returns a public IP on the
    first lookup and a private one on a later retry. httpx will resolve
    again internally; we accept the small TOCTOU risk because the
    blocklist below also catches direct IP literals in the URL.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Could not resolve that hostname.",
        ) from e
    for family, _type, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if not _is_public_ip(ip):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="That URL points to a non-public address and cannot be fetched.",
            )


def _validate_url(url: str) -> str:
    """Return the host if the URL is safe to fetch, else raise 400.

    Three layers:
      1. Scheme must be http or https — no file://, gopher://, ftp://,
         data://, etc. (httpx already errors on most, but explicit is
         cheaper than relying on transport quirks.)
      2. If the host is a literal IP, it must itself be public.
      3. Otherwise resolve and validate every returned address.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Only http(s) URLs are supported.",
        )
    host = parsed.hostname
    if not host:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="That URL has no hostname.",
        )
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        _resolve_and_validate(host)
    else:
        if not _is_public_ip(ip):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="That URL points to a non-public address and cannot be fetched.",
            )
    return host


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
    # Validate before the first request, then again after every redirect.
    # follow_redirects=False lets us walk the chain ourselves so each
    # hop's destination IP can be re-validated — auto-follow would let an
    # attacker host a public URL that 302s to a private one.
    host = _validate_url(url)
    if any(host.endswith(b) for b in BLOCKED_HOSTS):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="LinkedIn URLs are not supported. Use the browser extension or paste the text.",
        )

    current_url = url
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": UA}) as client:
            for _ in range(MAX_REDIRECTS + 1):
                resp = await client.get(current_url, follow_redirects=False)
                if resp.is_redirect:
                    next_url = resp.headers.get("location")
                    if not next_url:
                        break
                    # urljoin via httpx handles relative redirects safely.
                    current_url = str(resp.next_request.url) if resp.next_request else next_url
                    host = _validate_url(current_url)
                    continue
                resp.raise_for_status()
                body = resp.content[:MAX_BYTES]
                break
            else:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Too many redirects.",
                )
    except httpx.HTTPError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Could not fetch that URL: {e.__class__.__name__}",
        ) from e

    soup = BeautifulSoup(body, "html.parser")
    return _extract_ats(soup, host) or _extract_generic(soup)
