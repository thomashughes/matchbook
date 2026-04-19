"""
Prompt: given a parsed CV, produce up to 10 clarifying questions.

Four questions are mandatory (spec §3.2 step 2): work location, salary
expectation, remote preference, notice period. We instruct Claude to
*always* include these and to fill remaining slots with CV-specific
follow-ups. This keeps answers across users comparable for later
analytics while still being tailored.
"""

from pydantic import BaseModel, Field, field_validator

from app.services.ai_service import wrap_user_input


class Question(BaseModel):
    # Coerce id to string. Why: the prompt asks for slugs but Claude
    # frequently returns sequential integers (1, 2, 3). The downstream
    # UI only needs a stable opaque key per question, so we accept
    # either shape and normalise rather than fail the whole flow.
    id: str = Field(description="short slug, lowercase_snake")
    text: str
    # One of: work_location, salary, remote, notice, free_text.
    # Enables the UI to render dedicated inputs (e.g. currency) where useful.
    kind: str = "free_text"

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v: object) -> str:
        return str(v)


class ClarifyingQuestions(BaseModel):
    questions: list[Question]


SYSTEM = (
    "You generate a short, conversational interview. Output JSON: "
    "{questions:[{id,text,kind}]}. kind is one of: "
    "'location','salary','notice','free_text'. "
    "You MUST include exactly one question of each kind in "
    "{location, salary, notice}. The 'location' question must ask "
    "about BOTH geography AND remote/hybrid/office preference in a "
    "SINGLE question — never ask two separate questions about work "
    "arrangement. "
    "You MAY add up to 7 additional 'free_text' questions that would "
    "help a recruiter match this candidate. Each free_text question "
    "must cover a DIFFERENT topic — do not overlap with earlier "
    "questions or each other. Keep questions warm, concise, human. "
    "Do not ask more than 10 total."
)


def build_user_message(parsed_cv_json: str) -> str:
    return (
        "<task>Produce clarifying questions for this candidate.</task>\n"
        + wrap_user_input("candidate_profile", parsed_cv_json)
    )
