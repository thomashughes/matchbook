"""
Prompt: parse a raw CV into a structured object.

Kept as a separate module (not inlined in the route) because prompts are
assets — they are versioned, tweaked, A/B'd, and explained. Routing code
changes for different reasons than prompt wording; one file per prompt
keeps diffs legible.
"""

from pydantic import BaseModel, Field

from app.services.ai_service import wrap_user_input


class ParsedCV(BaseModel):
    """Schema Claude must conform to. Any deviation triggers a 500.

    Deliberately loose shapes (list[str], dict) where the CV content varies
    a lot between candidates (junior vs principal, tech vs design). Too-
    strict types would force Claude into awkward compromises.
    """

    name: str | None = None
    headline: str | None = Field(default=None, description="e.g. 'Senior Backend Engineer'")
    years_experience: int | None = None
    hard_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    education: list[dict] = Field(default_factory=list)
    roles: list[dict] = Field(default_factory=list)
    summary: str = ""


SYSTEM = (
    "You extract structured data from CVs/resumes. You respond ONLY with "
    "a JSON object matching this TypeScript shape:\n"
    "{ name: string|null, headline: string|null, years_experience: number|null, "
    "hard_skills: string[], soft_skills: string[], industries: string[], "
    "education: {institution, degree, years}[], "
    "roles: {company, title, start, end, summary}[], summary: string }\n"
    "No prose outside the JSON."
)


def build_user_message(cv_text: str) -> str:
    """Wrap the untrusted CV text in an XML tag before sending."""
    return (
        "<task>Extract a structured candidate profile from the CV below.</task>\n"
        + wrap_user_input("cv_text", cv_text)
    )
