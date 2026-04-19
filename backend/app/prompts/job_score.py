"""
Prompt: score a candidate profile against a job description.

The six dimensions and their weights are spec-defined (§3.4). We ask
Claude to return per-dimension scores out of 100 and compute the
weighted total OURSELVES — delegating arithmetic to Claude would
introduce rounding noise and occasional hallucinated maths. Claude
judges, we calculate.
"""

import json

from pydantic import BaseModel, Field, conint

from app.services.ai_service import wrap_user_input


# conint(ge=0, le=100): Pydantic enforces 0-100 at validation time, so a
# nonsense Claude score (e.g. 150) is caught before we persist it.
Score = conint(ge=0, le=100)


class JobScoreResponse(BaseModel):
    skills_score: Score  # type: ignore[valid-type]
    experience_score: Score  # type: ignore[valid-type]
    salary_score: Score  # type: ignore[valid-type]
    location_score: Score  # type: ignore[valid-type]
    culture_score: Score  # type: ignore[valid-type]
    trajectory_score: Score  # type: ignore[valid-type]

    strengths: list[str] = Field(default_factory=list, description="top 3")
    weaknesses: list[str] = Field(default_factory=list, description="top 3")
    red_flags: list[str] = Field(
        default_factory=list,
        description="Phrases detected: 'fast-paced', 'wear many hats', 'unlimited PTO', 'startup mentality', 'self-starter', 'family culture'. Surface-only, NOT a score deduction.",
    )
    summary: str = ""

    # Parsed salary range (from the JD text). Storing here too saves a
    # second Claude call later when the UI wants the range normalised.
    salary_min: int | None = None
    salary_max: int | None = None
    salary_raw: str | None = None

    # Extracted metadata. Why here (instead of a second call): the model
    # already has the JD loaded for scoring, so piggybacking title /
    # company / location extraction onto the same call is free.
    # `None` when the JD genuinely doesn't state it — callers keep any
    # user-provided values (from the UI form) and fall back to these.
    title: str | None = None
    company: str | None = None
    location: str | None = None


# Weights per §3.4. Change these ONLY with migration-like care — existing
# scores remain valid but become incomparable with new scores.
WEIGHTS = {
    "skills_score": 0.30,
    "experience_score": 0.20,
    "salary_score": 0.15,
    "location_score": 0.15,
    "culture_score": 0.10,
    "trajectory_score": 0.10,
}


def weighted_total(parts: JobScoreResponse) -> int:
    total = sum(getattr(parts, k) * w for k, w in WEIGHTS.items())
    # Round to nearest int for display; stored as INTEGER in DB.
    return int(round(total))


SYSTEM = (
    "You are a precise matching engine. Score the candidate against the "
    "job across six dimensions — skills, experience, salary, location, "
    "culture, trajectory — each 0-100. Also return up to 3 strengths, "
    "3 weaknesses, a one-paragraph summary, a red_flags list of vague "
    "or concerning phrases present in the JD ('fast-paced', 'wear many "
    "hats', 'unlimited PTO', 'startup mentality', 'self-starter', "
    "'family culture'), and the salary range if stated (min/max/raw). "
    "Also extract: title (the role name), company (hiring company), and "
    "location (city/country or 'Remote') — use null only if genuinely "
    "absent from the JD. "
    "Return JSON only. Do not compute the total; the caller does that."
)


def build_user_message(profile: dict, job_description: str) -> str:
    return (
        "<task>Score this candidate against this job.</task>\n"
        + wrap_user_input("candidate_profile", json.dumps(profile, ensure_ascii=False))
        + "\n"
        + wrap_user_input("job_description", job_description)
    )
