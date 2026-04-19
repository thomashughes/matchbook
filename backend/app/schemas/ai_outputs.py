"""
Pydantic schemas for the generic job AI outputs (outreach / form_response
/ follow_up / interview_prep). Cover letters have their own schemas.

Each kind has its own Pydantic input model — that keeps the validation
specific (Claude cares about the right knobs per kind), but they all
surface as the same `JobAIOutputOut` shape on the way back.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


Kind = Literal["outreach", "form_response", "follow_up", "interview_prep"]


class OutreachGenerateIn(BaseModel):
    channel: Literal["linkedin_connection", "linkedin_inmail", "email"] = "email"
    recipient_role: Literal[
        "hiring_manager", "recruiter", "team_member", "referral"
    ] = "hiring_manager"
    # Optional; when absent the prompt falls back to a neutral greeting.
    recipient_name: str | None = Field(default=None, max_length=120)


class FollowUpGenerateIn(BaseModel):
    # Stage is the single biggest driver of follow-up shape: a post-
    # interview thank-you reads nothing like a polite chase two weeks
    # into silence. Exposing it as a first-class enum lets Claude pick
    # the right template without us having to describe the situation
    # in free text.
    stage: Literal[
        "post_application",
        "post_interview",
        "post_recruiter_call",
        "no_response",
    ] = "post_application"
    # Email vs LinkedIn changes length, whether there's a subject line,
    # and register. Both default to a professional tone — a follow-up
    # is not the place for a "conversational" knob.
    channel: Literal["email", "linkedin"] = "email"
    # Optional specific thing the user wants referenced — most useful
    # post-interview ("the ownership model Sara described", "the book
    # she recommended") where a concrete callback makes the message
    # feel real instead of boilerplate. 500 chars is plenty.
    context: str | None = Field(default=None, max_length=500)


class InterviewPrepGenerateIn(BaseModel):
    # Round drives the whole question mix. A phone screen has almost
    # no deep-technical content; a final round skews toward vision and
    # strategy. "general" is for when you don't know what's next.
    round: Literal[
        "phone_screen",
        "technical",
        "behavioural",
        "final",
        "general",
    ] = "general"
    # Optional topic bias — "system design", "React hooks", "team
    # leadership". Short because it's a hint, not a spec.
    focus: str | None = Field(default=None, max_length=200)


class FormResponseGenerateIn(BaseModel):
    # Generous upper bound — users paste entire prompt blocks from
    # application forms ("Describe a time when… (max 500 words)"), not just
    # one-liners. 2000 chars keeps the prompt size sane without truncating
    # realistic questions.
    question: str = Field(..., min_length=3, max_length=2000)
    # Optional hard cap. When None, the prompt lets Claude pick a length
    # that matches the question's own framing (e.g. "in 200 words" → 200;
    # a short factual question → one or two sentences). Lower bound keeps
    # us above useless one-word answers; upper bound matches the longest
    # real-world form answer length we'd expect.
    max_words: int | None = Field(default=None, ge=20, le=1000)


class JobAIOutputOut(BaseModel):
    id: UUID
    job_id: UUID
    kind: str
    content: str
    params: dict
    version: int
    created_at: datetime
