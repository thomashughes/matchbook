"""
Prompt: generate a tailored interview-prep sheet for an upcoming round.

Unlike the other AI actions in this table, interview prep is NOT a
message the user sends. It's a study aid — a single document with
three clearly-named sections:

    1. Likely TECHNICAL questions (with brief how-to-approach hints).
    2. Likely BEHAVIOURAL questions (with STAR hooks from the
       candidate's actual experience).
    3. QUESTIONS TO ASK the interviewer (thoughtful, specific to this
       role/company, not boilerplate 'what's the team like?').

The round type changes the weighting heavily — a phone screen skews
motivation/fit, a technical round is 80% deep technical, a final round
leans strategy. Exposing `round` lets Claude pick the right mix without
us describing the situation in free text.

Output format: ALL-CAPS section headers underlined with a dash row, so
the result renders cleanly in a `whitespace-pre-wrap` card without
needing a markdown renderer on the frontend. That's a deliberate trade-
off: one extra day of polish to wire up markdown isn't worth blocking
the feature.
"""

import json

from app.services.ai_service import wrap_user_input


ROUNDS: dict[str, str] = {
    "phone_screen": (
        "Phone screen / recruiter screen. Technical content should be "
        "LIGHT — surface-level familiarity checks at most. Weight "
        "heaviest toward motivation, background fit, salary/location "
        "alignment, and basic role understanding. 2–3 technical, 4–6 "
        "behavioural/motivational, 5–6 questions to ask focused on "
        "process, next steps, and team shape."
    ),
    "technical": (
        "Technical round. 6–8 technical questions mapped to the "
        "stack/domain in the JD, each with a 1–2 line hint on how to "
        "approach it. 3–4 behavioural questions that could still come "
        "up (debugging under pressure, technical disagreements). 5–6 "
        "questions to ask about engineering practices, codebase, "
        "testing, incidents, tooling."
    ),
    "behavioural": (
        "Behavioural / values round. 3–4 technical questions at "
        "sanity-check level only. 6–8 behavioural questions with "
        "emphasis on leadership, conflict, growth, and failure — each "
        "with a STAR hook drawn from the candidate's actual profile "
        "where possible. 5–6 questions to ask about culture, feedback "
        "loops, autonomy, and team dynamics."
    ),
    "final": (
        "Final round / on-site. Mix of deep behavioural, strategy, "
        "and high-level technical. 4–5 technical (architecture, "
        "trade-offs, scale). 4–5 behavioural with executive presence "
        "(ownership, influence, tough calls). 5–7 questions to ask "
        "about company direction, investment in the team, what "
        "success at 12 months looks like, and how they measure it."
    ),
    "general": (
        "Round not specified. Produce a balanced general-purpose prep "
        "sheet: 4–5 technical, 4–5 behavioural, 5–6 questions to ask. "
        "Useful when the user doesn't yet know the format of the next "
        "conversation."
    ),
}


SYSTEM = (
    "You are preparing a specific candidate for a specific upcoming "
    "interview round. Use ONLY the candidate profile and job "
    "description to tailor the questions. Do not fabricate company "
    "details, interviewer names, or benchmarks.\n\n"
    "Produce exactly THREE sections, IN THIS ORDER, with headers in "
    "ALL CAPS on their own line, underlined with a row of em-dashes "
    "(—) of the same visual width:\n\n"
    "  TECHNICAL\n"
    "  —————————\n\n"
    "  BEHAVIOURAL\n"
    "  ———————————\n\n"
    "  QUESTIONS TO ASK\n"
    "  ————————————————\n\n"
    "In TECHNICAL and BEHAVIOURAL, number each question (1., 2., …) "
    "on its own line, followed by an indented 'Hint:' line with ONE "
    "to TWO short sentences on how to approach it. Behavioural hints "
    "should point to a STAR angle using the candidate's actual "
    "experience when possible ('Use the X rollout from Role Y'). "
    "Leave one blank line between items.\n\n"
    "In QUESTIONS TO ASK, use '- ' bullets. Each should be specific "
    "to this role/company — reference something from the JD when you "
    "can. Avoid boilerplate ('What's the team like?', 'What's a "
    "typical day?').\n\n"
    "If the user supplied a focus area, bias question selection toward "
    "it without ignoring the rest. Return ONLY the prep sheet — no "
    "preamble, no closing notes, no commentary about the process."
)


def build_user_message(
    profile: dict,
    job_description: str,
    *,
    round: str,
    focus: str | None,
    company: str | None,
    title: str | None,
) -> str:
    """Assemble the user-turn message for an interview-prep generation."""
    round_instruction = ROUNDS.get(round, ROUNDS["general"])
    header = (
        f"<task>Generate interview preparation for the role of "
        f"{title or 'this position'} at {company or 'this company'}."
        f"</task>\n"
        f"<round>{round}: {round_instruction}</round>\n"
    )
    focus_block = (
        wrap_user_input("focus", focus) + "\n"
        if focus and focus.strip()
        else ""
    )
    return (
        header
        + focus_block
        + wrap_user_input(
            "candidate_profile",
            json.dumps(profile, ensure_ascii=False),
        )
        + "\n"
        + wrap_user_input("job_description", job_description)
    )
