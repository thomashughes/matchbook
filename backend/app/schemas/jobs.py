"""Pydantic schemas for job CRUD + scoring."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


# --- Input ----------------------------------------------------------------


class JobCreateIn(BaseModel):
    """Unified create endpoint. Exactly one of description / url / ext
    should be supplied. Route logic picks based on source_type."""

    source_type: Literal["paste", "url", "extension"]
    description: str | None = Field(default=None, min_length=100)
    url: HttpUrl | None = None
    # From the browser extension: already-extracted fields from the page.
    title: str | None = None
    company: str | None = None


class JobPatch(BaseModel):
    status: (
        Literal["saved", "applied", "interviewing", "offer", "rejected"] | None
    ) = None
    notes: str | None = None


# --- Output ---------------------------------------------------------------


class JobScoreOut(BaseModel):
    total_score: int
    skills_score: int
    experience_score: int
    salary_score: int
    location_score: int
    culture_score: int
    trajectory_score: int
    strengths: list[str] | None
    weaknesses: list[str] | None
    red_flags: list[str] | None
    summary: str | None
    scored_at: datetime


class JobListItem(BaseModel):
    """Minimal shape for job list / dashboard. Score may be None while
    scoring is in progress, or on jobs created before scoring existed."""

    id: UUID
    title: str
    company: str
    location: str | None
    status: str
    source_type: str
    created_at: datetime
    total_score: int | None
    salary_raw: str | None


class JobDetailOut(BaseModel):
    id: UUID
    title: str
    company: str
    location: str | None
    salary_min: int | None
    salary_max: int | None
    salary_raw: str | None
    description_raw: str
    source_url: str | None
    source_type: str
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime
    score: JobScoreOut | None


class CompareOut(BaseModel):
    jobs: list[JobDetailOut]
