"""
AI-output routes — outreach / form_response / follow_up / interview_prep.

One table (`job_ai_outputs`), one list endpoint per job filtered by kind,
one DELETE by id, and kind-specific POSTs for generation so each has its
own input schema. Cover letters aren't here — see cover_letters.py.

Tenant isolation: every query filters on user_id. Job ownership is
checked once via _own_job before touching job_ai_outputs rows.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_verified_user, rate_limit_ai
from app.core.database import get_db
from app.models.job import Job
from app.models.job_ai_output import JobAIOutput
from app.models.profile import Profile
from app.models.user import User
from app.prompts import follow_up as follow_up_prompt
from app.prompts import form_response as form_response_prompt
from app.prompts import interview_prep as interview_prep_prompt
from app.prompts import outreach as outreach_prompt
from app.schemas.ai_outputs import (
    FollowUpGenerateIn,
    FormResponseGenerateIn,
    InterviewPrepGenerateIn,
    JobAIOutputOut,
    Kind,
    OutreachGenerateIn,
)
from app.services.ai_service import complete_text

router = APIRouter(prefix="/jobs/{job_id}/ai-outputs", tags=["ai-outputs"])


async def _own_job(job_id: UUID, user: User, db: AsyncSession) -> Job:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


async def _require_profile(user: User, db: AsyncSession) -> Profile:
    result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile is None or profile.structured_data is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Complete onboarding before generating AI actions.",
        )
    return profile


def _out(row: JobAIOutput) -> JobAIOutputOut:
    return JobAIOutputOut(
        id=row.id,
        job_id=row.job_id,
        kind=row.kind,
        content=row.content,
        params=row.params or {},
        version=row.version,
        created_at=row.created_at,
    )


async def _next_version(db: AsyncSession, job_id: UUID, kind: str) -> int:
    # Race is cosmetic — two concurrent generations getting the same
    # version number isn't worth a lock. Same rationale as cover letters.
    res = await db.execute(
        select(func.coalesce(func.max(JobAIOutput.version), 0)).where(
            JobAIOutput.job_id == job_id, JobAIOutput.kind == kind
        )
    )
    return int(res.scalar() or 0) + 1


@router.get("", response_model=list[JobAIOutputOut])
async def list_outputs(
    job_id: UUID,
    kind: Kind = Query(..., description="Which AI action to list versions for."),
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> list[JobAIOutputOut]:
    """List all versions of a given kind for a job, newest first."""
    await _own_job(job_id, user, db)
    result = await db.execute(
        select(JobAIOutput)
        .where(
            JobAIOutput.job_id == job_id,
            JobAIOutput.user_id == user.id,
            JobAIOutput.kind == kind,
        )
        .order_by(JobAIOutput.version.desc())
    )
    return [_out(r) for r in result.scalars().all()]


@router.delete(
    "/{output_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def remove(
    job_id: UUID,
    output_id: UUID,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single version. No renumbering of surviving versions."""
    await _own_job(job_id, user, db)
    result = await db.execute(
        delete(JobAIOutput).where(
            JobAIOutput.id == output_id,
            JobAIOutput.job_id == job_id,
            JobAIOutput.user_id == user.id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Output not found")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- kind-specific POSTs --------------------------------------------------
# Each kind gets its own endpoint + input schema so Pydantic validates the
# right fields. All routes converge on the same table + out schema.


@router.post(
    "/outreach",
    response_model=JobAIOutputOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_ai)],
)
async def generate_outreach(
    job_id: UUID,
    body: OutreachGenerateIn,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> JobAIOutputOut:
    """Generate a new outreach message version."""
    job = await _own_job(job_id, user, db)
    profile = await _require_profile(user, db)

    content = await complete_text(
        system=outreach_prompt.SYSTEM,
        user=outreach_prompt.build_user_message(
            profile.structured_data,
            job.description_raw,
            channel=body.channel,
            recipient_role=body.recipient_role,
            recipient_name=body.recipient_name,
            company=job.company,
            title=job.title,
        ),
        # Outreach is short; 1024 is plenty and caps runaway drafts.
        max_tokens=1024,
    )

    next_version = await _next_version(db, job.id, "outreach")
    row = JobAIOutput(
        job_id=job.id,
        user_id=user.id,
        kind="outreach",
        content=content,
        params={
            "channel": body.channel,
            "recipient_role": body.recipient_role,
            "recipient_name": body.recipient_name,
        },
        version=next_version,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _out(row)


@router.post(
    "/form-response",
    response_model=JobAIOutputOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_ai)],
)
async def generate_form_response(
    job_id: UUID,
    body: FormResponseGenerateIn,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> JobAIOutputOut:
    """Generate a tailored answer to one application-form question."""
    job = await _own_job(job_id, user, db)
    profile = await _require_profile(user, db)

    content = await complete_text(
        system=form_response_prompt.SYSTEM,
        user=form_response_prompt.build_user_message(
            profile.structured_data,
            job.description_raw,
            question=body.question,
            max_words=body.max_words,
            company=job.company,
            title=job.title,
        ),
        # 1536 comfortably holds a STAR answer (~400 words ≈ 600 tokens)
        # with headroom for the occasional longer essay prompt, while
        # still capping runaway drafts. Word-cap enforcement is soft —
        # Claude usually obeys the SYSTEM instruction but we don't hard-
        # truncate server-side; the user is in control of the edit.
        max_tokens=1536,
    )

    next_version = await _next_version(db, job.id, "form_response")
    row = JobAIOutput(
        job_id=job.id,
        user_id=user.id,
        kind="form_response",
        content=content,
        # Store the exact question + cap the user submitted so each
        # version card can show which question it answered (critical
        # context once there are 3+ questions-worth of drafts).
        params={
            "question": body.question,
            "max_words": body.max_words,
        },
        version=next_version,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _out(row)


@router.post(
    "/follow-up",
    response_model=JobAIOutputOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_ai)],
)
async def generate_follow_up(
    job_id: UUID,
    body: FollowUpGenerateIn,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> JobAIOutputOut:
    """Generate a new follow-up message version for the given stage."""
    job = await _own_job(job_id, user, db)
    profile = await _require_profile(user, db)

    content = await complete_text(
        system=follow_up_prompt.SYSTEM,
        user=follow_up_prompt.build_user_message(
            profile.structured_data,
            job.description_raw,
            stage=body.stage,
            channel=body.channel,
            context=body.context,
            company=job.company,
            title=job.title,
        ),
        # Follow-ups are shorter than cover letters and typically
        # shorter than outreach — 1024 is plenty and caps runaway
        # drafts if Claude decides to over-explain.
        max_tokens=1024,
    )

    next_version = await _next_version(db, job.id, "follow_up")
    row = JobAIOutput(
        job_id=job.id,
        user_id=user.id,
        kind="follow_up",
        content=content,
        # Persist all three knobs so the version card can show stage +
        # channel chips, and the user can see (or hover) the original
        # context snippet that shaped the draft.
        params={
            "stage": body.stage,
            "channel": body.channel,
            "context": body.context,
        },
        version=next_version,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _out(row)


@router.post(
    "/interview-prep",
    response_model=JobAIOutputOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_ai)],
)
async def generate_interview_prep(
    job_id: UUID,
    body: InterviewPrepGenerateIn,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> JobAIOutputOut:
    """Generate a new interview-prep sheet version for the given round."""
    job = await _own_job(job_id, user, db)
    profile = await _require_profile(user, db)

    content = await complete_text(
        system=interview_prep_prompt.SYSTEM,
        user=interview_prep_prompt.build_user_message(
            profile.structured_data,
            job.description_raw,
            round=body.round,
            focus=body.focus,
            company=job.company,
            title=job.title,
        ),
        # Interview prep is the longest of the AI actions — three
        # sections, ~12–18 items total, each with a hint or STAR
        # anchor. 2048 comfortably holds a thorough sheet while still
        # capping runaway output.
        max_tokens=2048,
    )

    next_version = await _next_version(db, job.id, "interview_prep")
    row = JobAIOutput(
        job_id=job.id,
        user_id=user.id,
        kind="interview_prep",
        content=content,
        params={
            "round": body.round,
            "focus": body.focus,
        },
        version=next_version,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _out(row)
