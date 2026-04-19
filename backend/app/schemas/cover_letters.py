"""Pydantic schemas for cover letter generation + version history."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


Tone = Literal["formal", "conversational"]
Length = Literal["short", "standard", "detailed"]


class CoverLetterGenerateIn(BaseModel):
    """User choices for a fresh generation. Tone + length are the only
    knobs; more would dilute the signal to Claude without meaningful
    user benefit."""

    tone: Tone = "conversational"
    length: Length = "standard"


class CoverLetterOut(BaseModel):
    id: UUID
    job_id: UUID
    content: str
    tone: str
    length: str
    version: int
    created_at: datetime
