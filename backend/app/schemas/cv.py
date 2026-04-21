"""Pydantic schemas for the CV generator endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


Tone = Literal["professional", "bold"]


class Phase1QuestionOut(BaseModel):
    """One question as rendered by the Phase-1 form component."""

    id: str
    text: str
    type: Literal["text", "textarea", "radio"]
    hint: str = ""
    options: list[str] = Field(default_factory=list)


class Phase1Out(BaseModel):
    """Response for POST /cv/phase-one."""

    questions: list[Phase1QuestionOut]


class Phase2Answer(BaseModel):
    """User-submitted answer for one question. Ties back to Phase 1 id."""

    id: str
    question: str
    answer: str


class CvContact(BaseModel):
    """Structured contact information collected alongside Phase-1
    answers. Each field is optional — the candidate can skip any line.
    Only fields with non-empty values are sent to Claude and rendered
    in the finished CV. The set is fixed in the frontend form
    (email/phone/location/linkedin/github/portfolio) — Claude does not
    ask about these separately."""

    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None


class Phase2In(BaseModel):
    """Body for POST /cv/phase-two.

    extra_notes maps to the UI's "Anything else you want to include?"
    free-text field; separated from answers so Claude can weight it
    differently (general context vs. targeted Q&A).

    regenerate_reason is required for version 2+; the UI enforces this
    with a modal and min-length validation before submit.
    """

    answers: list[Phase2Answer]
    tone: Tone = "professional"
    extra_notes: str = ""
    regenerate_reason: str | None = None
    contact: CvContact | None = None


class CvVersionOut(BaseModel):
    id: UUID
    version: int
    content_markdown: str
    tone: str
    profile_version: int
    regenerate_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class CvVersionPatch(BaseModel):
    """Body for PUT /cv/{id}. Only the markdown is editable; metadata
    stays stable after generation."""

    content_markdown: str
