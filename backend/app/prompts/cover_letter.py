"""
Prompt: generate a tailored cover letter for a specific job.

The letter is produced from three inputs: the structured candidate
profile (so tone, seniority, and strengths ring true to the CV), the
raw job description (so the letter references the actual role rather
than generic platitudes), and explicit user choices on tone + length.

We intentionally do NOT return JSON here — the downstream use is a
text field the user will paste or edit. Asking Claude for plain text
avoids structural boilerplate like {"content": "..."} which doesn't
buy us anything. `complete_text()` in ai_service handles this path.
"""

import json

from app.services.ai_service import wrap_user_input


# Tone menu is deliberately small: two clear choices rather than a
# slider. More options dilute the signal to Claude and confuse users.
TONES: dict[str, str] = {
    "formal": (
        "Measured, professional, no colloquialisms. Structure: opening "
        "paragraph stating interest, middle paragraphs with specific "
        "evidence, closing with a call to action."
    ),
    "conversational": (
        "Warm, first-person, still professional but with personality. "
        "Short paragraphs. Avoid corporate clichés."
    ),
}


LENGTHS: dict[str, str] = {
    "short":    "Around 150 words. Tight, punchy, three short paragraphs at most.",
    "standard": "Around 300 words. Four paragraphs.",
    "detailed": "Around 500 words. Up to six paragraphs, with specific project examples.",
}


SYSTEM = (
    "You are a skilled career writer producing a cover letter for a "
    "specific job application. Use ONLY information from the candidate "
    "profile and job description provided. Do not invent qualifications, "
    "tenure, or outcomes. If a required skill is missing, acknowledge it "
    "briefly and pivot to a demonstrated adjacent strength. "
    "Address the hiring team generically ('Dear Hiring Team,') unless a "
    "specific name is present in the job description. "
    "Return ONLY the letter body — no preamble, no signature block, no "
    "commentary. The caller will add name and contact details."
)


def build_user_message(
    profile: dict,
    job_description: str,
    *,
    tone: str,
    length: str,
    company: str | None,
    title: str | None,
) -> str:
    tone_instruction = TONES.get(tone, TONES["conversational"])
    length_instruction = LENGTHS.get(length, LENGTHS["standard"])
    header = (
        f"<task>Write a cover letter for the role of "
        f"{title or 'this position'} at {company or 'this company'}.</task>\n"
        f"<tone>{tone_instruction}</tone>\n"
        f"<length>{length_instruction}</length>\n"
    )
    return (
        header
        + wrap_user_input("candidate_profile", json.dumps(profile, ensure_ascii=False))
        + "\n"
        + wrap_user_input("job_description", job_description)
    )
