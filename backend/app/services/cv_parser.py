"""
CV file validation + text extraction.

Defence in depth (handoff §4.3):
    - size check before reading (memory + DoS)
    - python-magic signature check (can't be spoofed by extension or header)
    - pathlib.Path sanitisation on filename
    - storage outside web root (directory is supplied by the caller;
      caller uses UPLOADS_DIR from config)
    - text extraction via pdfplumber / python-docx — files never executed

If PDF text extraction yields <100 characters the file is likely an
image-scanned PDF (§3.2 step 1). Rather than OCR it here, we mark it
"needs_vision" and upstream code routes to Claude vision. Vision isn't
implemented in this module to keep responsibilities clean.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import magic
import pdfplumber
from docx import Document
from fastapi import HTTPException, status

MAX_BYTES = 5 * 1024 * 1024  # 5MB, matches spec

# MIME types from python-magic. We check signatures, NOT the browser-
# supplied Content-Type or filename extension — both are trivially forged.
ALLOWED_MIME = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    # python-magic sometimes reports Word documents as the generic
    # OOXML container — allow it and let python-docx fail if it's not
    # actually a Word file.
    "application/zip": "docx",
}

# Root directory for uploaded files. Outside any web root.
# The container mounts /var/matchbook/uploads from a named volume.
UPLOADS_ROOT = Path("/var/matchbook/uploads")


@dataclass
class ExtractedCV:
    path: Path
    text: str
    # True if extraction yielded very little text — upstream should
    # invoke a vision pipeline (Phase-2 stretch; not wired here).
    needs_vision: bool


def _validate_size(data: bytes) -> None:
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_BYTES // 1024 // 1024}MB limit",
        )


def _detect_kind(data: bytes) -> str:
    """Return 'pdf' or 'docx' — or raise 415 for anything else.

    We pass a sample of the bytes (not the whole buffer) for speed;
    libmagic only needs the first few hundred bytes.
    """
    mime = magic.from_buffer(data[:4096], mime=True)
    kind = ALLOWED_MIME.get(mime)
    if not kind:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF or Word (.docx) CVs are accepted.",
        )
    return kind


def _extract_pdf(data: bytes) -> str:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages).strip()


def _extract_docx(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs).strip()


def _user_dir(user_id: UUID) -> Path:
    """Per-user directory under uploads root. Created if needed.

    The path is constructed from the user's UUID via Path() so a crafted
    user id literally cannot traverse (UUIDs don't contain slashes, and
    Path rejects them anyway). Belt and braces.
    """
    d = UPLOADS_ROOT / "cvs" / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def extract_pdf_text(data: bytes) -> str:
    """Validate → extract text from a PDF, without persisting to disk.

    Used by the Add-Job PDF upload flow where the PDF itself is not
    worth keeping once we've pulled out the description — unlike the CV
    which users might want to re-process. Same validation posture as
    `save_and_extract` (size + signature) so a malformed upload fails
    fast with a sensible status code.
    """
    _validate_size(data)
    kind = _detect_kind(data)
    if kind != "pdf":
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are supported for job descriptions.",
        )
    return _extract_pdf(data)


def save_and_extract(user_id: UUID, filename: str, data: bytes) -> ExtractedCV:
    """Validate → save → extract. Returns path+text+vision-fallback flag.

    Old CV is overwritten on re-upload (§4.3): we always write to
    'cv.<ext>' so a user has at most one CV file on disk at a time.
    """
    _validate_size(data)
    kind = _detect_kind(data)

    # Sanitise the filename via Path — never trust client-supplied names.
    # We only use the extension from the detected kind; the original
    # filename is ignored entirely for the on-disk path.
    safe_path = _user_dir(user_id) / f"cv.{kind}"
    safe_path.write_bytes(data)

    text = _extract_pdf(data) if kind == "pdf" else _extract_docx(data)
    return ExtractedCV(
        path=safe_path,
        text=text,
        needs_vision=(kind == "pdf" and len(text) < 100),
    )
