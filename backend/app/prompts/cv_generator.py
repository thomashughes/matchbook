"""
Prompt: two-phase CV rewrite.

Phase 1 — Claude reads the parsed CV and generates 8-12 targeted
clarifying questions in a structured list so the frontend can render
typed inputs (text / textarea / radio) without string parsing.

Phase 2 — Claude rewrites the CV in full using the user's answers as
editorial brief. Output is Markdown (`##` section headings, `**` bold
for role/employer, `-` bullets) rather than plain text, so the TipTap
editor and the WeasyPrint PDF renderer share one canonical format.

Hallucination guardrails are explicit in the system prompt:
    - Banned-word list (no "leverage", "delve", "tapestry", etc.).
    - No em-dashes anywhere.
    - Inline [VERIFY: ...] flags for anything not supported by the CV
      or the user's answers. The frontend renders these as warning pills
      so the user cannot miss them.
    - Inline [REWRITE: ...] tags for major changes to the original,
      so the user sees why each edit happened.

The prompt content itself is Thomas's — years of iteration on what
actually produces CVs that land interviews. Do not water it down.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from app.services.ai_service import wrap_user_input


# --- Phase 1 schema --------------------------------------------------------


class Phase1Question(BaseModel):
    """A single clarifying question rendered in the Phase-1 form.

    `type` dictates the input widget. `options` is required for radio;
    ignored for text/textarea. We keep `id` short (q1..qN) so the frontend
    can key answers without trusting Claude to invent stable slugs.
    """

    id: str = Field(..., description="Short id like 'q1'..'q12'")
    text: str = Field(..., description="The question itself")
    type: Literal["text", "textarea", "radio"]
    hint: str = Field(default="", description="Helper copy under the input")
    options: list[str] = Field(
        default_factory=list,
        description="Radio choices; empty for text/textarea",
    )


class Phase1Output(BaseModel):
    """Top-level schema Claude must return in Phase 1."""

    questions: list[Phase1Question]


# --- Phase 1 system prompt -------------------------------------------------


PHASE_ONE_SYSTEM = (
    "You are a senior talent agent and technical CV editor. A candidate "
    "has uploaded their CV. Your job right now is Phase 1: generate "
    "between 10 and 14 targeted questions to gather ALL information "
    "needed for a finished CV the candidate can download and send "
    "immediately. The CV that follows this step must contain NO "
    "uncertain claims and NO placeholder text. If any fact in the CV "
    "lacks evidence (specific dates, quantified outcomes, exact job "
    "titles, team sizes, company names), you MUST ask about it here.\n"
    "\n"
    "Required coverage:\n"
    "- Target role, seniority level, and industry (if unclear or worth "
    "confirming).\n"
    "- Target salary range and location preferences (if missing from "
    "the CV).\n"
    "- Which projects or roles to emphasise vs. de-emphasise.\n"
    "- SPECIFIC METRICS for the candidate's biggest achievements — "
    "revenue, users, time saved, team size, growth percentages, "
    "delivery speed. Ask the candidate to quantify anything in the CV "
    "phrased as a generality (e.g. 'improved performance' → ask for "
    "the actual figure).\n"
    "- EXACT DATES for every role if the CV uses vague ranges ('2022-"
    "present' is fine; '2 years ago' is not).\n"
    "- Employment gaps or career pivots that need honest reframing.\n"
    "- Skills the CV undersells or omits entirely.\n"
    "- Anything outdated, irrelevant, or they would rather not lead "
    "with.\n"
    "- Tone and positioning preference.\n"
    "- Whether they are applying to one specific role or keeping the "
    "CV general.\n"
    "\n"
    "Guiding principle: after this step Claude must have everything to "
    "write a CV WITHOUT any [VERIFY] markers. If in doubt, ask.\n"
    "\n"
    "The candidate is asked about contact details (email, phone, "
    "location, LinkedIn, GitHub, portfolio) through a separate UI form "
    "— do NOT include questions about those.\n"
    "\n"
    "Ids must be q1..qN in order. For radio questions provide 2-5 "
    "options. Never invent new output keys. Output only the questions "
    "in the required JSON schema — no preamble, no commentary."
)


def phase_one_user_message(parsed_cv: dict) -> str:
    return wrap_user_input(
        "parsed_cv", json.dumps(parsed_cv, ensure_ascii=False)
    )


# --- Phase 2 system prompt -------------------------------------------------


PHASE_TWO_SYSTEM = (
    "You are a senior talent agent and technical CV editor. The "
    "candidate has uploaded their CV, answered your Phase-1 questions, "
    "and told you which contact links to include. Your job now is to "
    "produce the candidate's finished CV — something they can download "
    "and send to an employer today, with no further review required.\n"
    "\n"
    "STRICT RULES\n"
    "1. Banned words: delve, tapestry, pivotal, testament, "
    "comprehensive, tailored (as a verb), leverage (as a verb), "
    "navigate, foster, seamlessly, spearheaded, orchestrated, synergy, "
    "holistic, robust (as filler). If a sentence reads like a robot "
    "wrote it, rewrite it.\n"
    "2. No em-dashes anywhere. Use colons, commas, semicolons, or full "
    "stops.\n"
    "3. Every bullet should follow the X-Y-Z formula where evidence "
    "supports it: Accomplished [X] as measured by [Y], by doing [Z].\n"
    "4. Maximum two pages of content (~800-1000 words). No objective "
    "statements. Every word earns its place. Cut the weakest bullets "
    "first if over length.\n"
    "5. Punchy, active language. An experienced professional talking "
    "shop, not a marketing brochure.\n"
    "6. UK English spelling throughout.\n"
    "7. No rhythmic triplet structures. No overly balanced or mirrored "
    "sentences.\n"
    "8. DO NOT invent metrics, skills, or project details not supported "
    "by the CV or the candidate's answers. If information is missing, "
    "OMIT the claim — do not flag it, do not add placeholders, do not "
    "use [VERIFY] or [REWRITE] or any other in-line marker. The output "
    "goes straight to an employer.\n"
    "9. Preserve the structural flow of the original (Profile, "
    "Experience, Skills, Education) unless a change clearly improves "
    "readability.\n"
    "10. Lead with the strongest material. De-prioritise what the "
    "candidate flagged as weak rather than removing it entirely.\n"
    "\n"
    "TONE\n"
    "If the caller specified tone=professional, default to measured, "
    "confident, understated. If tone=bold, allow sharper verbs and a "
    "more confident first-person voice, while keeping every other rule.\n"
    "\n"
    "OUTPUT\n"
    "Output the full CV as Markdown:\n"
    "- Begin with the candidate's name as a level-1 heading (#).\n"
    "- A single contact line directly under the name as italic text, "
    "assembled from ONLY the contact fields the candidate chose to "
    "include. Separate with a middle dot (·). Omit any fields marked "
    "as skipped. Example: 'jane@example.co.uk · +44 7700 900000 · "
    "London · linkedin.com/in/jane-doe'. Do NOT invent contact info.\n"
    "- Section headings as level-2 (##): Profile, Experience, Skills, "
    "Education (and others if warranted).\n"
    "- Role headings as level-3 (###) with role title, employer, "
    "location, and dates. Use a bold line for the title/employer and "
    "italic dates on the next line if it reads cleaner than inline.\n"
    "- Bullets as `- ` dashed lists.\n"
    "Do not wrap the output in a code fence. Do not add any preamble, "
    "sign-off, or commentary outside the CV itself. Output ONLY the CV."
)


def phase_two_user_message(
    parsed_cv: dict,
    answers: list[dict],
    *,
    tone: str,
    extra_notes: str,
    regenerate_reason: str | None,
    contact: dict | None = None,
) -> str:
    """Build the Phase-2 user message.

    Layout:
        <tone> and <regenerate_reason> are meta-directives at the top so
        Claude weights them before reading the data payloads.
        <contact> carries only the fields the candidate chose to include;
        the prompt instructs Claude to use them verbatim and omit any
        that are missing.
        <parsed_cv> + <answers> + <extra_notes> are data, XML-wrapped
        per the service-layer defence rules.
    """
    lines: list[str] = []
    lines.append(f"<tone>{tone}</tone>")
    if regenerate_reason:
        lines.append(
            "<regenerate_reason>"
            "The candidate was not satisfied with the previous draft. "
            "Pay attention to this guidance: "
            f"{regenerate_reason}"
            "</regenerate_reason>"
        )
    if contact:
        lines.append(
            wrap_user_input(
                "contact",
                json.dumps(contact, ensure_ascii=False),
            )
        )
    lines.append(wrap_user_input("parsed_cv", json.dumps(parsed_cv, ensure_ascii=False)))
    lines.append(wrap_user_input("answers", json.dumps(answers, ensure_ascii=False)))
    if extra_notes:
        lines.append(wrap_user_input("extra_notes", extra_notes))
    return "\n".join(lines)
