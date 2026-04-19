"""
Prompt: generate a follow-up message tied to a specific job and stage in
the hiring process.

Follow-ups are a different animal from outreach. Outreach opens a door;
follow-ups maintain a thread that already exists. That means the message
must match what just happened (did I just interview? apply? get ghosted
for a fortnight?) and stay brief — a wordy follow-up is a bad follow-up.

The SYSTEM teaches Claude the general rules (short, no fabrication, no
guilt-tripping on silence). STAGES carries the per-stage template. The
channel controls length and whether there's a subject line.

Stored under job_ai_outputs (kind="follow_up"); shares the generic
routes/model with outreach + form_response.
"""

import json

from app.services.ai_service import wrap_user_input


STAGES: dict[str, str] = {
    "post_application": (
        "Stage: polite check-in ~1–3 weeks after submitting the "
        "application. Reaffirm interest in the specific role, reference "
        "one concrete fit-point from the candidate's profile that maps "
        "to the job, and offer to answer questions. Do NOT pressure for "
        "a decision or a timeline. Assume the reader is busy."
    ),
    "post_interview": (
        "Stage: thank-you sent within 24 hours of an interview. Open "
        "with a warm, specific thank-you. If the user supplied context "
        "(a topic from the conversation, a recommendation, a question "
        "that came up), reference it concretely — that's what makes the "
        "message feel real. Reiterate fit in one line, not a re-pitch "
        "of the whole CV. Close with enthusiasm for next steps. No "
        "grovelling."
    ),
    "post_recruiter_call": (
        "Stage: immediate thank-you after a recruiter screen or intake "
        "call. Thank the recruiter, restate the one or two alignment "
        "points the call surfaced (salary band fit, availability, scope "
        "match), and confirm readiness for the next step. Short and "
        "businesslike — recruiters want to move forward, not read."
    ),
    "no_response": (
        "Stage: respectful nudge after silence (2+ weeks with no reply "
        "on an active thread). Acknowledge they're busy, restate "
        "interest, and signal it's fine if the role has moved on or "
        "timing has changed — that framing makes a reply psychologically "
        "easier. No guilt-tripping, no 'just following up again', no "
        "implication they owe a response. Keep it very short."
    ),
}


CHANNELS: dict[str, str] = {
    "email": (
        "Email. 120–180 words. Subject line on its own first line "
        "prefixed 'Subject: '. Then a greeting, 2–3 short paragraphs, "
        "and a closing line. No signature block — the user adds their "
        "own sign-off."
    ),
    "linkedin": (
        "LinkedIn message. 80–120 words. No subject line. One or two "
        "short paragraphs. Friendly-professional register."
    ),
}


SYSTEM = (
    "You are writing a follow-up message on behalf of a candidate for a "
    "specific job at a specific point in the hiring process. Use ONLY "
    "facts present in the candidate profile, the job description, and "
    "the optional context the user supplied. Do not invent interviewers' "
    "names, meetings that did not happen, or outcomes that were not "
    "mentioned.\n\n"
    "Follow-ups live or die on brevity and specificity. A generic "
    "follow-up reads as AI-generated; a specific one reads as real. "
    "Pick ONE concrete thing to anchor the message (a fit-point, a "
    "topic from the interview, a salary-fit confirmation from the "
    "call) rather than summarising multiple things.\n\n"
    "Never pressure the reader for a reply, deadline, or decision. "
    "Never open with 'I hope this email finds you well' or similar "
    "filler. Return ONLY the message body (with a Subject line where "
    "the channel calls for one) — no commentary, no preamble, no "
    "signature block."
)


def build_user_message(
    profile: dict,
    job_description: str,
    *,
    stage: str,
    channel: str,
    context: str | None,
    company: str | None,
    title: str | None,
) -> str:
    """Assemble the user-turn for a follow-up generation.

    The optional `context` is wrapped in its own XML tag rather than
    concatenated into the task header — same prompt-injection logic as
    the form_response question: user-supplied text is data, not
    instructions, even when it says things like 'write this as if…'.
    """
    stage_instruction = STAGES.get(stage, STAGES["post_application"])
    channel_instruction = CHANNELS.get(channel, CHANNELS["email"])
    header = (
        f"<task>Write a follow-up message for the role of "
        f"{title or 'this position'} at {company or 'this company'}."
        f"</task>\n"
        f"<stage>{stage}: {stage_instruction}</stage>\n"
        f"<channel>{channel}: {channel_instruction}</channel>\n"
    )
    context_block = (
        wrap_user_input("user_context", context) + "\n"
        if context and context.strip()
        else ""
    )
    return (
        header
        + context_block
        + wrap_user_input(
            "candidate_profile",
            json.dumps(profile, ensure_ascii=False),
        )
        + "\n"
        + wrap_user_input("job_description", job_description)
    )
