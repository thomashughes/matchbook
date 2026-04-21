"""
CV Markdown → PDF rendering via WeasyPrint.

Why WeasyPrint:
    - Pure-Python; no headless browser in the container (Playwright +
      Chromium would add ~300MB to the image).
    - CSS Paged Media support: @page rules give us A4, margins, and
      running headers/footers without hacks.
    - Mature Unicode handling for international names.

Font note:
    WeasyPrint uses system fonts. The backend image must include at
    least one serif and one sans-serif with broad Unicode coverage; the
    Dockerfile installs `fonts-liberation` and `fonts-dejavu` to cover
    that. Without those fonts, WeasyPrint renders a tofu warning in the
    PDF — which would silently produce bad exports.

Markdown pipeline:
    Markdown → HTML via markdown_it (no HTML passthrough, so a malicious
    CV can't inject script tags) → HTML wrapped in a neutral CV template
    → rendered by WeasyPrint. The [VERIFY:] and [REWRITE:] inline tags
    are stripped at PDF time — they're editor-only UI affordances, not
    part of the candidate's final CV.

This module is pure: no DB, no HTTP. The route at /cv/{id}/pdf calls
render_pdf(markdown, candidate_name) and streams the bytes back.
"""

from __future__ import annotations

import re

from markdown_it import MarkdownIt
from weasyprint import CSS, HTML


# markdown_it with HTML rendering disabled. Stored markdown is user-
# derived (Claude output edited by the user), so we treat it as
# untrusted. html=False drops any raw HTML the source contains; linkify
# is off because a CV should not sprout auto-links mid-line.
_MD = MarkdownIt("commonmark", {"html": False, "linkify": False})


# [VERIFY: ...] and [REWRITE: ...] are editor-only flags. Strip before
# PDF so the candidate never accidentally exports them. Case-insensitive,
# tolerates whitespace and multi-line notes.
_EDITOR_FLAG_RE = re.compile(
    r"\[(?:VERIFY|REWRITE)\s*:\s*[^\]]*\]",
    re.IGNORECASE,
)


def _strip_editor_flags(md: str) -> str:
    """Remove inline [VERIFY:] and [REWRITE:] markers from the markdown.

    They are intentionally loud in the editor (red badges) so the user
    reviews every unverified claim. Once they hit "Export PDF" we assume
    the user has addressed them or explicitly chosen to proceed; the
    exported document should not carry debug markup.
    """
    return _EDITOR_FLAG_RE.sub("", md)


# Inline CSS for the CV. Kept inside the module rather than a separate
# .css file so rendering is self-contained — easier to test, no path
# resolution surprises in containers. Rule of thumb: change only when
# you have a specific typographic defect in a rendered CV.
_CV_CSS = """
@page {
    size: A4;
    margin: 18mm 16mm 16mm 16mm;
}
html, body {
    font-family: "Liberation Serif", "DejaVu Serif", Georgia, serif;
    font-size: 10.5pt;
    line-height: 1.35;
    color: #111;
}
h1 {
    font-family: "Liberation Sans", "DejaVu Sans", Helvetica, sans-serif;
    font-size: 20pt;
    margin: 0 0 2pt 0;
    letter-spacing: 0.2pt;
}
h2 {
    font-family: "Liberation Sans", "DejaVu Sans", Helvetica, sans-serif;
    font-size: 12pt;
    text-transform: uppercase;
    letter-spacing: 1.2pt;
    border-bottom: 0.5pt solid #444;
    margin: 14pt 0 6pt 0;
    padding-bottom: 2pt;
}
h3 {
    font-family: "Liberation Sans", "DejaVu Sans", Helvetica, sans-serif;
    font-size: 11pt;
    margin: 8pt 0 2pt 0;
}
p, li { margin: 0 0 3pt 0; }
ul { padding-left: 14pt; margin: 0 0 6pt 0; }
li { margin-bottom: 2pt; }
em { color: #444; font-style: normal; }
strong { font-weight: 600; }
a { color: #111; text-decoration: none; }
"""


def render_pdf(markdown_src: str) -> bytes:
    """Render a Markdown CV to PDF bytes.

    Caller (the route) is responsible for setting Content-Type and
    Content-Disposition headers — this function is pure. Returns the
    full PDF as bytes because WeasyPrint writes to a buffer anyway and
    CVs are small enough (<200KB) that streaming is unnecessary.

    Raises:
        ValueError: if markdown_src is empty. We'd rather fail loudly
        than render a blank PDF that a user might send to an employer.
    """
    src = _strip_editor_flags(markdown_src).strip()
    if not src:
        raise ValueError("Cannot render an empty CV.")

    body_html = _MD.render(src)
    full_html = (
        "<!DOCTYPE html>"
        '<html lang="en">'
        "<head><meta charset=\"utf-8\"></head>"
        f"<body>{body_html}</body>"
        "</html>"
    )
    return HTML(string=full_html).write_pdf(
        stylesheets=[CSS(string=_CV_CSS)]
    )
