"""
Profile / onboarding routes.

Flow (§3.2):
    1. POST /profile/upload-cv      → extract text, parse via Claude,
                                     create/replace profile row with
                                     parsed CV stored in structured_data.
    2. GET  /profile/questions      → Claude generates clarifying Qs.
    3. POST /profile/answers        → persist answers, generate final
                                     profile, merge into profiles row.
    4. GET  /profile                → fetch the current profile.
    5. PATCH /profile               → manual edits (§3.2 "editable after
                                     creation").
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_verified_user,
    rate_limit_ai,
    rate_limit_cv_upload,
)
from app.core.database import get_db
from app.models.profile import Profile, ProfileAnswer
from app.models.user import User
from app.prompts import clarifying_questions as cq_prompt
from app.prompts import cv_parse as cv_prompt
from app.prompts import profile_generate as pg_prompt
from app.schemas.profile import (
    AnswersIn,
    CVUploadOut,
    ProfileOut,
    ProfilePatch,
    QuestionsOut,
)
from app.services.ai_service import complete_json, scan_for_injection
from app.services.cv_parser import save_and_extract

router = APIRouter(prefix="/profile", tags=["profile"])


# --- 1. Upload CV ---------------------------------------------------------


@router.post(
    "/upload-cv",
    response_model=CVUploadOut,
    dependencies=[Depends(rate_limit_cv_upload), Depends(rate_limit_ai)],
)
async def upload_cv(
    file: UploadFile = File(...),
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> CVUploadOut:
    """Validate → save → extract → parse with Claude.

    The heavy work (file hashing, Claude call) is done inline rather than
    queued for simplicity — typical end-to-end is ~5s, well within an
    HTTP request budget. Phase 5 can move this to a background job if
    average latency grows.
    """
    data = await file.read()
    extracted = save_and_extract(user.id, file.filename or "cv", data)

    # If we got very little text, vision fallback would be wired here in
    # a later iteration. For now, refuse so the user knows to re-upload.
    if extracted.needs_vision:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Couldn't read text from that PDF — it may be an image scan. "
                   "Please upload a text-based PDF or a Word document.",
        )

    # Soft injection signal — log but don't block, since CVs can
    # legitimately contain triggering terms (e.g. a security engineer
    # describing their work).
    hits = scan_for_injection(extracted.text)
    if hits:
        # Intentionally not raising; see ai_service comments.
        pass

    parsed = await complete_json(
        system=cv_prompt.SYSTEM,
        user=cv_prompt.build_user_message(extracted.text),
        schema=cv_prompt.ParsedCV,
    )

    # Upsert the profile row. "At most one profile per user" is a soft
    # invariant we enforce at the app layer, not the DB — easier to
    # relax later if we want multi-CV support.
    existing = await db.execute(select(Profile).where(Profile.user_id == user.id))
    profile = existing.scalar_one_or_none()
    if profile is None:
        profile = Profile(user_id=user.id)
        db.add(profile)

    profile.cv_raw_text = extracted.text
    profile.cv_file_path = str(extracted.path)
    profile.structured_data = parsed.model_dump()
    profile.skills_hard = parsed.hard_skills
    profile.skills_soft = parsed.soft_skills

    # Clear any stale clarifying-question answers from a previous CV —
    # a fresh CV means the questions will be regenerated against the
    # new parse, so old answers may no longer apply.
    await db.execute(delete(ProfileAnswer).where(ProfileAnswer.user_id == user.id))

    await db.commit()
    await db.refresh(profile)

    return CVUploadOut(
        profile_id=profile.id,
        extracted_chars=len(extracted.text),
        cv_needs_vision=extracted.needs_vision,
    )


# --- 2. Clarifying questions ---------------------------------------------


@router.get(
    "/questions",
    response_model=QuestionsOut,
    dependencies=[Depends(rate_limit_ai)],
)
async def get_questions(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> QuestionsOut:
    result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile is None or profile.structured_data is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Upload a CV first."
        )

    import json as _json
    parsed_cv_json = _json.dumps(profile.structured_data, ensure_ascii=False)
    qs = await complete_json(
        system=cq_prompt.SYSTEM,
        user=cq_prompt.build_user_message(parsed_cv_json),
        schema=cq_prompt.ClarifyingQuestions,
    )
    return QuestionsOut(questions=[q.model_dump() for q in qs.questions])  # type: ignore[arg-type]


# --- 3. Submit answers, generate final profile ---------------------------


@router.post(
    "/answers",
    response_model=ProfileOut,
    dependencies=[Depends(rate_limit_ai)],
)
async def submit_answers(
    body: AnswersIn,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile is None or profile.structured_data is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Upload a CV first."
        )

    # Persist answers first so we have an audit trail even if generation
    # fails partway — the user didn't lose their typing.
    for ans in body.answers:
        db.add(
            ProfileAnswer(user_id=user.id, question=ans.question, answer=ans.answer)
        )
    await db.flush()

    generated = await complete_json(
        system=pg_prompt.SYSTEM,
        user=pg_prompt.build_user_message(
            profile.structured_data, [a.model_dump() for a in body.answers]
        ),
        schema=pg_prompt.GeneratedProfile,
    )

    # Merge into the profile row. We deliberately DON'T overwrite
    # structured_data (which still holds the raw CV parse) — useful for
    # later re-analysis. Instead we set the typed columns.
    profile.seniority_level = generated.seniority_level
    profile.salary_min = generated.salary_min
    profile.salary_ideal = generated.salary_ideal
    profile.location_preferences = generated.location_preferences
    profile.remote_preference = generated.remote_preference
    profile.notice_period = generated.notice_period
    profile.career_goals = generated.career_goals
    profile.skills_hard = generated.hard_skills
    profile.skills_soft = generated.soft_skills
    profile.structured_data = {
        **(profile.structured_data or {}),
        "generated": generated.model_dump(),
    }

    await db.commit()
    await db.refresh(profile)
    return _profile_out(profile)


# --- 4. Get / patch -------------------------------------------------------


@router.get("", response_model=ProfileOut)
async def get_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No profile yet.")
    return _profile_out(profile)


@router.patch("", response_model=ProfileOut)
async def patch_profile(
    body: ProfilePatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No profile yet.")

    # Apply only provided (non-None) fields. model_dump(exclude_unset=True)
    # differentiates "user sent null" from "user omitted" — we treat them
    # the same here (no field may be cleared via PATCH), but the pattern
    # is worth noting.
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(profile, key, value)

    await db.commit()
    await db.refresh(profile)
    return _profile_out(profile)


def _profile_out(p: Profile) -> ProfileOut:
    return ProfileOut(
        id=p.id,
        seniority_level=p.seniority_level,
        hard_skills=p.skills_hard,
        soft_skills=p.skills_soft,
        salary_min=p.salary_min,
        salary_ideal=p.salary_ideal,
        remote_preference=p.remote_preference,
        notice_period=p.notice_period,
        career_goals=p.career_goals,
        structured_data=p.structured_data,
    )
