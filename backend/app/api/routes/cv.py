"""
CV generator routes.

Two-phase flow:
    Phase 1: POST /cv/phase-one
        Reads the user's parsed CV, asks Claude for 8-12 tailored
        clarifying questions, returns them to the frontend. Cheap — no
        quota cost. Rate-limited by the standard AI bucket.
    Phase 2: POST /cv/phase-two
        Takes the user's answers + chosen tone + optional
        regenerate_reason, calls Claude for a full CV rewrite, persists
        as a new cv_versions row. Costs ONE cv_generation credit.
        Refund-on-failure; same transactional pattern as cover letters.

Editing:
    PUT  /cv/{id} — user-edited markdown overwrites content_markdown.
                    No new version — edits are tracked against the
                    existing row so the version list stays clean.
    DELETE /cv/{id} — confirm-guarded in UI.

Export:
    GET /cv/{id}/pdf       — WeasyPrint renders the Markdown.
    GET /cv/{id}/markdown  — raw markdown download.

Tenant isolation: every query filters on user_id. The path parameter
{cv_id} is validated by matching it against the current user's rows
before any read/write.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import entitlement, get_verified_user, rate_limit_ai
from app.core.database import get_db
from app.core.entitlements import refund, remaining
from app.models.cv_version import CvVersion
from app.models.profile import Profile
from app.models.user import User
from app.prompts import cv_generator as cv_prompt
from app.schemas.cv import (
    CvVersionOut,
    CvVersionPatch,
    Phase1Out,
    Phase1QuestionOut,
    Phase2In,
)
from app.services.ai_service import complete_json, complete_text
from app.services.cv_pdf import render_pdf

router = APIRouter(prefix="/cv", tags=["cv"])


# --- helpers --------------------------------------------------------------


async def _require_profile(user: User, db: AsyncSession) -> Profile:
    """Fetch the user's profile or 400 if not onboarded.

    CV generation needs a parsed CV to start from — without it, Phase 1
    has nothing to ask about and Phase 2 has nothing to rewrite.
    """
    result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile is None or profile.structured_data is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Upload and finish your profile before generating a CV.",
        )
    return profile


def _out(row: CvVersion) -> CvVersionOut:
    return CvVersionOut(
        id=row.id,
        version=row.version,
        content_markdown=row.content_markdown,
        tone=row.tone,
        profile_version=row.profile_version,
        regenerate_reason=row.regenerate_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _own_cv(cv_id: UUID, user: User, db: AsyncSession) -> CvVersion:
    """Fetch a CV version, 404ing if it doesn't belong to the caller.

    Same ownership-verification pattern as cover_letters._own_job — the
    per-user filter lives in the query, not a post-hoc if-check.
    """
    result = await db.execute(
        select(CvVersion).where(
            CvVersion.id == cv_id, CvVersion.user_id == user.id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="CV version not found")
    return row


# --- Phase 1 --------------------------------------------------------------


@router.post(
    "/phase-one",
    response_model=Phase1Out,
    dependencies=[Depends(rate_limit_ai)],
)
async def phase_one(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> Phase1Out:
    """Generate clarifying questions. Does NOT consume a credit.

    Phase 1 is cheap compared to Phase 2 (short JSON output, no 2000-
    token CV rewrite). Charging for it would make the feature feel
    punishing ("I burned a credit just to see what you'd ask me").
    """
    profile = await _require_profile(user, db)

    result = await complete_json(
        system=cv_prompt.PHASE_ONE_SYSTEM,
        user=cv_prompt.phase_one_user_message(profile.structured_data),
        schema=cv_prompt.Phase1Output,
    )
    return Phase1Out(
        questions=[
            Phase1QuestionOut(**q.model_dump()) for q in result.questions
        ]
    )


# --- Phase 2 --------------------------------------------------------------


@router.post(
    "",
    response_model=CvVersionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit_ai),
        Depends(entitlement("cv_generation", "user")),
    ],
)
async def generate(
    body: Phase2In,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> CvVersionOut:
    """Rewrite the CV and persist a new version.

    Credit is consumed by the entitlement dep BEFORE we enter here; on
    any failure (validation, Anthropic error, DB error) we refund via
    the standard try/except/refund pattern.

    Regenerate reason is required once the user has at least one
    existing version this cycle. The UI enforces this with a modal;
    the backend does NOT hard-fail without it, because we accept the
    user's first-generation case where reason is legitimately absent.
    """
    try:
        profile = await _require_profile(user, db)

        md = await complete_text(
            system=cv_prompt.PHASE_TWO_SYSTEM,
            user=cv_prompt.phase_two_user_message(
                profile.structured_data,
                [a.model_dump() for a in body.answers],
                tone=body.tone,
                extra_notes=body.extra_notes,
                regenerate_reason=body.regenerate_reason,
            ),
            # CV output can run long on detailed histories; 4096 is our
            # standard cap but two-page CVs occasionally push it with the
            # [REWRITE] annotations appended. 6000 gives headroom without
            # inviting sprawl.
            max_tokens=6000,
        )

        # Next version = current max + 1. The UNIQUE (user_id, version)
        # constraint catches the concurrent-generation race — the losing
        # request gets an IntegrityError and the refund path kicks in.
        max_v = await db.execute(
            select(func.coalesce(func.max(CvVersion.version), 0)).where(
                CvVersion.user_id == user.id
            )
        )
        next_version = int(max_v.scalar() or 0) + 1

        row = CvVersion(
            user_id=user.id,
            version=next_version,
            content_markdown=md,
            tone=body.tone,
            questions_payload={
                "answers": [a.model_dump() for a in body.answers],
                "extra_notes": body.extra_notes,
            },
            regenerate_reason=body.regenerate_reason,
            profile_version=user.profile_version,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return _out(row)
    except Exception:
        await refund(db, user, "cv_generation", scope_key=None)
        raise


# --- Read + edit ----------------------------------------------------------


@router.get("", response_model=list[CvVersionOut])
async def list_versions(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> list[CvVersionOut]:
    """List the user's CV versions, newest first."""
    result = await db.execute(
        select(CvVersion)
        .where(CvVersion.user_id == user.id)
        .order_by(CvVersion.version.desc())
    )
    return [_out(r) for r in result.scalars().all()]


@router.get("/{cv_id}", response_model=CvVersionOut)
async def get_one(
    cv_id: UUID,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> CvVersionOut:
    row = await _own_cv(cv_id, user, db)
    return _out(row)


@router.put("/{cv_id}", response_model=CvVersionOut)
async def save_edits(
    cv_id: UUID,
    body: CvVersionPatch,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> CvVersionOut:
    """Save the user's inline edits in place. No new version created.

    Updates the existing row's content_markdown and bumps updated_at.
    Not charged — editing is free; Claude is the scarce resource.
    """
    row = await _own_cv(cv_id, user, db)
    row.content_markdown = body.content_markdown
    await db.commit()
    await db.refresh(row)
    return _out(row)


@router.delete(
    "/{cv_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def remove(
    cv_id: UUID,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a version. Confirm-guarded in the UI.

    Does NOT refund a credit — the generation happened, Claude was paid,
    the user just decided they didn't like the result enough to keep it.
    Mirrors cover-letter deletion semantics.
    """
    result = await db.execute(
        delete(CvVersion).where(
            CvVersion.id == cv_id, CvVersion.user_id == user.id
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="CV version not found")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Export ---------------------------------------------------------------


@router.get("/{cv_id}/pdf")
async def export_pdf(
    cv_id: UUID,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the CV as a PDF via WeasyPrint.

    Filename includes the version number so a user with multiple drafts
    can tell them apart on disk. No personally-identifying info in the
    filename; the CV itself carries the candidate's name.
    """
    row = await _own_cv(cv_id, user, db)
    pdf_bytes = render_pdf(row.content_markdown)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="cv-v{row.version}.pdf"'
            ),
        },
    )


@router.get("/{cv_id}/markdown")
async def export_markdown(
    cv_id: UUID,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download the raw Markdown source so users can edit outside the app."""
    row = await _own_cv(cv_id, user, db)
    return Response(
        content=row.content_markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="cv-v{row.version}.md"'
            ),
        },
    )


# --- Status ---------------------------------------------------------------


@router.get("/status/quota")
async def quota_status(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return remaining cv_generation credits for the current window.

    Separate from /billing/status so the CV page can fetch just this
    number without loading the full usage block.
    """
    n = await remaining(db, user, "cv_generation", scope_key=None)
    return {"remaining": n}
