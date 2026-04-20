"""
Cover letter routes — generate, list, and delete versions.

Each generation creates a new row in `cover_letters`. We never overwrite
a prior version: the whole point of the history is the user can compare
tone + length choices, or go back to a draft they liked after tweaking
Claude's output. Pruning is explicit via DELETE.

Tenant isolation: every query filters on user_id. Job ownership is
verified once per request via _own_job before touching the cover_letters
table.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import entitlement, get_verified_user, rate_limit_ai
from app.core.database import get_db
from app.core.entitlements import refund
from app.models.cover_letter import CoverLetter
from app.models.job import Job
from app.models.profile import Profile
from app.models.user import User
from app.prompts import cover_letter as cl_prompt
from app.schemas.cover_letters import CoverLetterGenerateIn, CoverLetterOut
from app.services.ai_service import complete_text

router = APIRouter(prefix="/jobs/{job_id}/cover-letters", tags=["cover-letters"])


async def _own_job(job_id: UUID, user: User, db: AsyncSession) -> Job:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


def _out(row: CoverLetter) -> CoverLetterOut:
    return CoverLetterOut(
        id=row.id,
        job_id=row.job_id,
        content=row.content,
        tone=row.tone,
        length=row.length,
        version=row.version,
        created_at=row.created_at,
    )


@router.post(
    "",
    response_model=CoverLetterOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit_ai),
        Depends(entitlement("cover_letter", "job")),
    ],
)
async def generate(
    job_id: UUID,
    body: CoverLetterGenerateIn,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> CoverLetterOut:
    """Generate a new cover letter version.

    Pulls the profile + job, runs the prompt through complete_text (plain
    string, no JSON overhead), and persists as the next version number.
    """
    try:
        job = await _own_job(job_id, user, db)

        prof = await db.execute(select(Profile).where(Profile.user_id == user.id))
        profile = prof.scalar_one_or_none()
        if profile is None or profile.structured_data is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Complete onboarding before generating a cover letter.",
            )

        content = await complete_text(
            system=cl_prompt.SYSTEM,
            user=cl_prompt.build_user_message(
                profile.structured_data,
                job.description_raw,
                tone=body.tone,
                length=body.length,
                company=job.company,
                title=job.title,
            ),
            # Letters can run long on 'detailed'; give headroom so we never
            # truncate mid-sentence.
            max_tokens=2048,
        )

        # Next version = current max + 1. A SELECT MAX race is harmless here:
        # worst case two concurrent generations get the same version number,
        # which is cosmetic, and we accept it per the model's comment.
        max_v = await db.execute(
            select(func.coalesce(func.max(CoverLetter.version), 0)).where(
                CoverLetter.job_id == job.id
            )
        )
        next_version = int(max_v.scalar() or 0) + 1

        row = CoverLetter(
            job_id=job.id,
            user_id=user.id,
            content=content,
            tone=body.tone,
            length=body.length,
            version=next_version,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return _out(row)
    except Exception:
        await refund(db, user, "cover_letter", scope_key=job_id)
        raise


@router.get("", response_model=list[CoverLetterOut])
async def list_versions(
    job_id: UUID,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> list[CoverLetterOut]:
    """List all versions for a job, newest first."""
    await _own_job(job_id, user, db)
    result = await db.execute(
        select(CoverLetter)
        .where(CoverLetter.job_id == job_id, CoverLetter.user_id == user.id)
        .order_by(CoverLetter.version.desc())
    )
    return [_out(r) for r in result.scalars().all()]


@router.delete(
    "/{letter_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def remove(
    job_id: UUID,
    letter_id: UUID,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single version. No cascade or renumbering.

    No return annotation because FastAPI refuses to declare a response
    body on a 204 route (assertion at import time). We return an empty
    Response explicitly to keep the intent clear.
    """
    await _own_job(job_id, user, db)
    result = await db.execute(
        delete(CoverLetter).where(
            CoverLetter.id == letter_id,
            CoverLetter.job_id == job_id,
            CoverLetter.user_id == user.id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cover letter not found")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
