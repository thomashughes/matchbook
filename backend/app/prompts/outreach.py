"""
Prompt: generate an outreach message to a hiring contact for a specific job.

Shape of the output matches the channel — LinkedIn connection requests
are limited to ~300 characters, so 'connection' gets a tight one-
paragraph brief; InMail/email can stretch. Recipient role changes what
evidence Claude leads with: a hiring manager wants outcomes, a recruiter
wants fit + availability, a team member wants craft + curiosity.
"""

import json

from app.services.ai_service import wrap_user_input


CHANNELS: dict[str, str] = {
    "linkedin_connection": (
        "LinkedIn connection request note. Hard cap: 280 characters. "
        "One short paragraph. No salutation, no signature. Warm, "
        "specific, ends with a soft ask."
    ),
    "linkedin_inmail": (
        "LinkedIn InMail. 120–180 words. Subject line on its own first "
        "line prefixed 'Subject: '. Then 2–3 short paragraphs."
    ),
    "email": (
        "Professional email. 150–220 words. Subject line on its own "
        "first line prefixed 'Subject: '. Then greeting, 2–3 "
        "paragraphs, and a closing line (no signature block)."
    ),
}


RECIPIENT_ROLES: dict[str, str] = {
    "hiring_manager": (
        "Lead with one concrete, relevant outcome from the candidate's "
        "background. Reference the team's mandate. Ask for a brief chat."
    ),
    "recruiter": (
        "Lead with fit against the role's must-haves and availability. "
        "Mention whether they're currently open/closing-out elsewhere."
    ),
    "team_member": (
        "Lead with genuine curiosity about the work — a specific "
        "technology, project, or problem the team owns. Ask about day-to-"
        "day, not process."
    ),
    "referral": (
        "Lead with the connection (mutual interest/background). Short, "
        "low-pressure ask: would they be open to a quick intro?"
    ),
}


SYSTEM = (
    "You are writing outreach on behalf of a candidate to a contact "
    "related to a specific job. Use ONLY facts present in the candidate "
    "profile and job description. Do not fabricate tenure, projects, or "
    "mutual acquaintances. If the recipient name is 'Unknown', use a "
    "light generic greeting appropriate to the channel. "
    "Return ONLY the message body (with a Subject line where the channel "
    "calls for one). No commentary, no preamble, no signature block — "
    "the user adds their own sign-off."
)


def build_user_message(
    profile: dict,
    job_description: str,
    *,
    channel: str,
    recipient_role: str,
    recipient_name: str | None,
    company: str | None,
    title: str | None,
) -> str:
    channel_instruction = CHANNELS.get(channel, CHANNELS["email"])
    role_instruction = RECIPIENT_ROLES.get(recipient_role, RECIPIENT_ROLES["hiring_manager"])
    header = (
        f"<task>Write outreach for the role of {title or 'this position'} "
        f"at {company or 'this company'}.</task>\n"
        f"<recipient_name>{recipient_name or 'Unknown'}</recipient_name>\n"
        f"<recipient_role>{recipient_role}: {role_instruction}</recipient_role>\n"
        f"<channel>{channel}: {channel_instruction}</channel>\n"
    )
    return (
        header
        + wrap_user_input("candidate_profile", json.dumps(profile, ensure_ascii=False))
        + "\n"
        + wrap_user_input("job_description", job_description)
    )
