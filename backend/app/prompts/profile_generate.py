"""
Prompt: merge parsed CV + answered clarifying questions into the final
candidate profile that gets stored on the profiles table.

Why this is a separate prompt (not a one-shot from CV → profile):
    The clarifying-question step is genuinely useful — it pulls out
    preferences the CV never contains (salary, notice, remote). Skipping
    it would produce a weaker profile, which would then produce weaker
    scoring on every future job.
"""

import json

from pydantic import BaseModel, Field

from app.services.ai_service import wrap_user_input


class GeneratedProfile(BaseModel):
    """Target shape of the structured_data column on profiles."""

    # Default to "Mid" rather than required. Why: Claude sometimes omits
    # the field when the CV spans multiple seniorities or is early-career
    # (e.g. student projects). Failing the whole generation over that is
    # worse UX than a neutral default the user can edit on the profile page.
    seniority_level: str = Field(
        default="Mid", description="e.g. Junior, Mid, Senior, Staff, Principal"
    )
    industries: list[str] = Field(default_factory=list)
    hard_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    salary_min: int | None = None
    salary_ideal: int | None = None
    salary_currency: str = "GBP"
    location_preferences: dict = Field(
        default_factory=dict,
        description="{'cities':[], 'regions':[], 'timezone':str}",
    )
    remote_preference: str = Field(
        default="flexible",
        description="one of: remote_only, hybrid, office_only, flexible",
    )
    notice_period: str | None = None
    working_style: str = ""
    career_goals: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


SYSTEM = (
    "You synthesise a canonical candidate profile from a parsed CV and "
    "the candidate's answers to clarifying questions. Respond ONLY with "
    "JSON matching the schema the caller provided. Prefer explicit "
    "answers over inferences from the CV; use the CV to fill gaps."
)


def build_user_message(parsed_cv: dict, answers: list[dict]) -> str:
    """answers: list of {question, answer, kind?}"""
    return (
        "<task>Produce the final candidate profile.</task>\n"
        + wrap_user_input("parsed_cv", json.dumps(parsed_cv, ensure_ascii=False))
        + "\n"
        + wrap_user_input("answers", json.dumps(answers, ensure_ascii=False))
    )
