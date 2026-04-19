"""
Prompt: answer a single application-form question using the candidate's
profile and the target job description.

Application-form questions vary wildly in shape — "Why this role?"
(short, specific), "Describe a time you led through conflict"
(behavioural / STAR), "Are you authorised to work in the UK?" (one-line
factual), "What interests you about our mission?" (open-ended, warm).
Blasting every question with a generic 200-word paragraph is exactly
what makes AI-generated form answers read as AI-generated.

So the SYSTEM teaches Claude to recognise the question's shape and
match it: STAR in prose for behaviourals, tight paragraph for "why",
one or two sentences for factuals. When the user supplies a word cap
we pass it through as a hard limit; otherwise Claude infers length
from the question itself (which often embeds a hint — "in 200 words",
"three sentences") and falls back to ~150 words.

This lives under `job_ai_outputs` (kind="form_response") rather than a
dedicated table because it shares the exact shape as outreach/follow-
up/interview-prep: prompt-configured input, text blob out, versioned
per (job, kind). See app/models/job_ai_output.py for the rationale.
"""

import json

from app.services.ai_service import wrap_user_input


SYSTEM = (
    "You are answering ONE question on a job application form on "
    "behalf of a candidate. Use ONLY facts present in the candidate "
    "profile and job description. Do not fabricate experience, dates, "
    "outcomes, employers, or qualifications. If the candidate's profile "
    "genuinely lacks relevant evidence, write an honest answer that "
    "leans on adjacent experience rather than inventing specifics.\n\n"
    "Match the question's style:\n"
    "- Behavioural / 'tell me about a time…' / 'describe a situation "
    "where…' → compact STAR in flowing prose (Situation, Task, Action, "
    "Result). Do NOT use labelled section headers. One specific "
    "example beats three vague ones.\n"
    "- 'Why this role / company / team' → tight, specific answer that "
    "pairs concrete candidate evidence with concrete job facts. No "
    "boilerplate enthusiasm.\n"
    "- Factual / eligibility / preference (work auth, notice period, "
    "salary) → one or two direct sentences. Do not pad.\n"
    "- Open-ended motivation → first person, warm, specific to this "
    "role — not a statement that could apply to any company.\n\n"
    "If the question embeds a length hint ('in 200 words', 'three "
    "sentences', 'briefly') honour it. If the user supplied a hard "
    "word cap, treat it as the ceiling — stay under it. Otherwise aim "
    "for ~150 words. Return ONLY the answer body — do not restate the "
    "question, do not add a preamble, do not add a sign-off."
)


def build_user_message(
    profile: dict,
    job_description: str,
    *,
    question: str,
    max_words: int | None,
    company: str | None,
    title: str | None,
) -> str:
    """Assemble the user-turn message for a form-response generation.

    The question is wrapped in <form_question> so Claude treats it as
    data to answer rather than instructions to follow — some real form
    prompts literally read 'Write as if you were…' which is a prompt-
    injection foothold if we don't wrap it.
    """
    length_line = (
        f"<length>Hard cap: {max_words} words. Stay under this.</length>\n"
        if max_words is not None
        else ""
    )
    header = (
        f"<task>Answer this application-form question for the role of "
        f"{title or 'this position'} at {company or 'this company'}."
        f"</task>\n"
        + length_line
    )
    return (
        header
        + wrap_user_input("form_question", question)
        + "\n"
        + wrap_user_input(
            "candidate_profile",
            json.dumps(profile, ensure_ascii=False),
        )
        + "\n"
        + wrap_user_input("job_description", job_description)
    )
