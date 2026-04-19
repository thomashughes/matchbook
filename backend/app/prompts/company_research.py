"""
Prompt: research a company via Claude web search to produce a prep-for-
interview briefing.

Runs with the web_search_20250305 server tool — Claude issues searches
autonomously, reads results, and returns a single text response with
labelled sections. No JSON schema here: the response is long-form prose
structured by ALL-CAPS headers (same pattern as interview_prep) so the
UI can render it with a plain `whitespace-pre-wrap` block without
needing a markdown parser.

The SYSTEM prompt is written to be *refusal-friendly under sparse data*:
if searches turn up little (unknown stealth-mode companies, very small
firms), Claude is instructed to say so rather than pad with speculation.
Hallucinated "facts" about a real company are worse than an honest
"couldn't find much" because the user might walk into an interview
quoting them.
"""


SYSTEM = (
    "You are preparing a candidate to interview at a specific company. "
    "Use the web_search tool to research the company, then write a "
    "briefing grounded ONLY in what your searches returned. Do not "
    "invent facts, product details, funding rounds, employee numbers, "
    "or leadership names. If searches turn up little, say so plainly — "
    "sparse information is far more useful than confident speculation.\n\n"
    "Produce EXACTLY these sections, IN THIS ORDER, with headers in "
    "ALL CAPS on their own line, underlined by a row of em-dashes (—) "
    "of the same visual width:\n\n"
    "  OVERVIEW\n"
    "  ————————\n"
    "  Two or three sentences: what the company does, who it serves, "
    "scale signals (employee count range, geography, funding stage) "
    "where those are publicly reported.\n\n"
    "  RECENT NEWS\n"
    "  ———————————\n"
    "  3–5 bulleted items from the last ~12 months. Prefix each with a "
    "rough date ('2025 Q3 —', 'Last month —') when you can. Funding, "
    "product launches, leadership changes, layoffs, pivots. Skip this "
    "section entirely (with a short 'Nothing material surfaced.' note) "
    "if searches return nothing relevant — do not pad.\n\n"
    "  TECH & PRODUCT\n"
    "  ——————————————\n"
    "  What the product is, who uses it, and any public stack signals "
    "(job ads, engineering blog, conference talks). Mark stack guesses "
    "as such — 'Job ads mention Go + Kubernetes' is fine; 'They use "
    "Go + Kubernetes' is not unless the source is authoritative.\n\n"
    "  CULTURE & VALUES\n"
    "  ————————————————\n"
    "  Signals from the careers page, leadership posts, and independent "
    "reviews (Glassdoor, Blind, press). Note divergences between stated "
    "values and what reviewers report — honest tension is more useful "
    "than a sanitised summary.\n\n"
    "  INTERVIEW PROCESS\n"
    "  —————————————————\n"
    "  What candidates report: typical stages, common question themes, "
    "turnaround time, difficulty signals. Mark as 'Candidate reports:' "
    "so the reader knows the source shape. Skip with a note if nothing "
    "surfaces.\n\n"
    "  QUESTIONS TO PROBE\n"
    "  ——————————————————\n"
    "  5–7 bulleted questions the candidate could ask during interviews "
    "to pressure-test what surfaced above (e.g. 'Glassdoor mentions X "
    "attrition — how has retention trended since?'). These are for the "
    "candidate's notes, not to be read verbatim — frame them as probes, "
    "not accusations.\n\n"
    "  SOURCES\n"
    "  ———————\n"
    "  Bulleted list of the key URLs you drew from, one per line, with "
    "a short label. If no web_search calls returned useful results, "
    "state that explicitly and the briefing above should be short.\n\n"
    "Return ONLY the briefing — no preamble, no 'Here is the research', "
    "no closing remarks."
)


def build_user_message(*, company: str, job_description: str | None) -> str:
    """Build the user-turn for a company-research request.

    The job description is optional context — it helps Claude bias the
    research toward the relevant team/product where a company has many
    ('the team hiring for this role builds X') rather than generic
    company-wide research. If we don't have a JD we skip the block.

    The company name itself is NOT XML-wrapped because it's not
    untrusted user input in the same sense as a pasted CV — it's a
    short identifier the user typed for their own job. A malicious
    company name isn't a meaningful threat model (the user is the only
    victim of their own prompt-injection attempt here), and wrapping it
    would waste tokens on a tag Claude has to parse around.
    """
    ctx_block = ""
    if job_description and job_description.strip():
        from app.services.ai_service import wrap_user_input

        ctx_block = (
            "The candidate is interviewing for this specific role — "
            "bias your research toward the relevant team/product where "
            "the company is large enough for that to matter:\n"
            + wrap_user_input("job_description", job_description)
            + "\n\n"
        )
    return (
        f"Research the company '{company}' for interview preparation. "
        f"Use web_search as many times as needed (up to your limit) to "
        f"build an accurate picture.\n\n"
        + ctx_block
        + "Produce the briefing using the exact section structure the "
        "system prompt specifies."
    )
