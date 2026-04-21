"""Pydantic schemas for profile / onboarding routes."""

from uuid import UUID

from pydantic import BaseModel, Field


class QuestionOut(BaseModel):
    id: str
    text: str
    kind: str


class QuestionsOut(BaseModel):
    questions: list[QuestionOut]


class AnswerIn(BaseModel):
    question: str
    answer: str
    kind: str = "free_text"


class AnswersIn(BaseModel):
    # Max 12 = up to 10 Claude-generated questions + the optional
    # "anything else" free-form note + headroom.
    answers: list[AnswerIn] = Field(min_length=1, max_length=12)


class ProfileOut(BaseModel):
    id: UUID
    seniority_level: str | None
    hard_skills: list[str] | None
    soft_skills: list[str] | None
    salary_min: int | None
    salary_ideal: int | None
    remote_preference: str | None
    notice_period: str | None
    career_goals: str | None
    structured_data: dict | None
    # True once the user has run through CV upload AND clarifying-question
    # answers (i.e. structured_data.generated exists). Drives the
    # "Continue onboarding" top-bar banner: shown when False.
    onboarding_complete: bool = False
    # Current profile version; every rebuild increments this on the user
    # row. Frontend compares to per-artefact profile_version to show the
    # "generated against a previous profile" stale banners.
    profile_version: int = 1


class ProfilePatch(BaseModel):
    """Fields users can edit manually. Matches handoff §3.2 step 3."""

    seniority_level: str | None = None
    salary_min: int | None = None
    salary_ideal: int | None = None
    remote_preference: str | None = None
    notice_period: str | None = None
    career_goals: str | None = None
    hard_skills: list[str] | None = None
    soft_skills: list[str] | None = None
    location_preferences: dict | None = None


class CVUploadOut(BaseModel):
    """Result of uploading a CV. cv_needs_vision signals that text
    extraction was sparse and a future vision pipeline should be run."""

    profile_id: UUID
    extracted_chars: int
    cv_needs_vision: bool
