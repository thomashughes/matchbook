"""
Jobs routes — create (paste/url/extension), list, get, patch, delete,
re-score, and compare.

Scoring happens inline on job creation. §3.4 also permits re-scoring
via POST /jobs/{id}/score (after a profile update), implemented here.

Tenant isolation (§4.4): every query filters on user_id at the ORM
layer. No row returned from a query here should ever belong to a
different user — verified by the get-or-404 helper `_own_job`.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import entitlement, get_current_user, get_verified_user, rate_limit_ai
from app.core.database import get_db
from app.core.entitlements import RESOURCES, current_window, plan_limit, refund
from app.models.usage_counter import UsageCounter
from app.models.job import Job
from app.models.job_score import JobScore
from app.models.profile import Profile
from app.models.user import User
from app.prompts import job_score as js_prompt
from app.schemas.jobs import (
    CompareOut,
    JobCreateIn,
    JobDetailOut,
    JobListItem,
    JobPatch,
    JobQuotaItem,
    JobScoreOut,
)
from app.services.ai_service import complete_json
from app.services.cv_parser import extract_pdf_text
from app.services.url_scraper import scrape_job_url

router = APIRouter(prefix="/jobs", tags=["jobs"])


# --- Helpers --------------------------------------------------------------


async def _own_job(job_id: UUID, user: User, db: AsyncSession) -> Job:
    """Fetch a job and verify it belongs to the caller. 404 if not.

    Returning 404 (not 403) on someone else's job is deliberate: it
    leaks less information than 403 would (a 403 implicitly confirms
    the id exists, just not for you).
    """
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


async def _latest_score(job_id: UUID, db: AsyncSession) -> JobScore | None:
    result = await db.execute(
        select(JobScore)
        .where(JobScore.job_id == job_id)
        .order_by(JobScore.scored_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _score_out(s: JobScore | None) -> JobScoreOut | None:
    if s is None:
        return None
    return JobScoreOut(
        total_score=s.total_score,
        skills_score=s.skills_score,
        experience_score=s.experience_score,
        salary_score=s.salary_score,
        location_score=s.location_score,
        culture_score=s.culture_score,
        trajectory_score=s.trajectory_score,
        strengths=s.strengths,
        weaknesses=s.weaknesses,
        red_flags=s.red_flags,
        summary=s.summary,
        scored_at=s.scored_at,
    )


def _detail_out(
    job: Job,
    score: JobScore | None,
    quota: list[JobQuotaItem] | None = None,
) -> JobDetailOut:
    return JobDetailOut(
        id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_raw=job.salary_raw,
        description_raw=job.description_raw,
        source_url=job.source_url,
        source_type=job.source_type,
        status=job.status,
        notes=job.notes,
        created_at=job.created_at,
        updated_at=job.updated_at,
        score=_score_out(score),
        scored_against_profile_version=job.scored_against_profile_version,
        quota=quota or [],
    )


async def _job_quota(
    user: User, job_id: UUID, db: AsyncSession
) -> list[JobQuotaItem]:
    """Return the per-job quota snapshot used by the UI to caption
    generate buttons (e.g. "2 drafts left this month").

    Only per-job resources (scope='job') appear — per-user resources
    live on /billing/status so we don't duplicate them on every job
    detail response.

    One round trip: fetch all counter rows for (user, window, this job)
    and merge with RESOURCES to fill zeros where the user hasn't used
    that resource yet.
    """
    start, end = current_window(user)

    rows = (
        await db.execute(
            select(UsageCounter.resource, UsageCounter.count).where(
                UsageCounter.user_id == user.id,
                UsageCounter.window_start == start,
                UsageCounter.scope_key == job_id,
            )
        )
    ).all()
    by_resource: dict[str, int] = {r: int(c) for r, c in rows}

    items: list[JobQuotaItem] = []
    for key, spec in RESOURCES.items():
        if spec.scope != "job":
            continue
        used = by_resource.get(key, 0)
        limit = plan_limit(user, key)
        items.append(
            JobQuotaItem(
                resource=key,
                limit=limit,
                used=used,
                remaining=(None if limit is None else max(limit - used, 0)),
                resets_at=end,
            )
        )
    return items


async def _score_and_persist(
    job: Job, profile: Profile, db: AsyncSession, user: User | None = None
) -> JobScore:
    """Run the scoring prompt, persist a JobScore row, update job fields.

    Also writes parsed salary info back onto the job — §3.4 asks that
    Claude extract and normalise the salary range during scoring.

    The user argument is optional only for back-compat with the few call
    sites that don't have a User handy; when provided, we stamp the
    job's scored_against_profile_version so the UI can show a stale-
    score banner when the user later rebuilds their profile.
    """
    profile_payload = profile.structured_data or {}
    result = await complete_json(
        system=js_prompt.SYSTEM,
        user=js_prompt.build_user_message(profile_payload, job.description_raw),
        schema=js_prompt.JobScoreResponse,
    )

    total = js_prompt.weighted_total(result)

    row = JobScore(
        job_id=job.id,
        user_id=job.user_id,
        total_score=total,
        skills_score=result.skills_score,
        experience_score=result.experience_score,
        salary_score=result.salary_score,
        location_score=result.location_score,
        culture_score=result.culture_score,
        trajectory_score=result.trajectory_score,
        strengths=result.strengths,
        weaknesses=result.weaknesses,
        red_flags=result.red_flags,
        summary=result.summary,
    )
    db.add(row)

    # Snapshot the profile version the score was produced against, so
    # the UI can flag this score as stale if the user rebuilds their
    # profile later. Falls back to current-value-on-job if no user
    # passed — preserves "never-scored" (NULL) semantics.
    if user is not None:
        job.scored_against_profile_version = user.profile_version

    # Populate salary on the job itself so listings can show it without
    # joining through the score table.
    if result.salary_min is not None and job.salary_min is None:
        job.salary_min = result.salary_min
    if result.salary_max is not None and job.salary_max is None:
        job.salary_max = result.salary_max
    if result.salary_raw and not job.salary_raw:
        job.salary_raw = result.salary_raw

    # Fill title / company / location from extraction only if the caller
    # didn't already have them (URL scrape or user-typed values win).
    # We also overwrite the "Untitled role" / "Unknown company" fallbacks
    # that `create_job` writes when nothing is known up front.
    if result.title and job.title in (None, "", "Untitled role"):
        job.title = result.title
    if result.company and job.company in (None, "", "Unknown company"):
        job.company = result.company
    if result.location and not job.location:
        job.location = result.location

    return row


# --- Create ---------------------------------------------------------------


@router.post(
    "",
    response_model=JobDetailOut,
    # Order matters: rate_limit_ai first (cheap, Redis) fails fast on
    # abuse; entitlement second (DB write) only runs if we're under the
    # burst cap. Both must pass. Entitlement consumes a "jobs_created"
    # credit BEFORE we touch Anthropic — the refund on failure is in
    # the route body below.
    dependencies=[Depends(rate_limit_ai), Depends(entitlement("jobs_created"))],
)
async def create_job(
    body: JobCreateIn,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> JobDetailOut:
    # Refund-on-failure: the entitlement dep has already CONSUMED a
    # 'jobs_created' credit. If ANYTHING in this body fails — scrape
    # error, too-short description, Anthropic 5xx, DB constraint — we
    # must put that credit back. Otherwise a user who hit "Add Job"
    # with a junk URL would silently burn credits on retry.
    try:
        # Resolve description + title + company based on source type.
        title: str | None = body.title
        company: str | None = body.company
        description: str
        url: str | None = None

        if body.source_type == "paste":
            if not body.description:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="description is required for paste")
            description = body.description
        elif body.source_type == "url":
            if not body.url:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="url is required")
            url = str(body.url)
            scraped = await scrape_job_url(url)
            description = scraped.description
            if not title:
                title = scraped.title
            if not company:
                company = scraped.company
        elif body.source_type == "extension":
            if not body.description:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="extension must send description")
            description = body.description
        else:  # defensive — Pydantic Literal should prevent this.
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="unsupported source_type")

        if len(description) < 100:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Job description is too short (min 100 characters).",
            )

        # Need a profile to score against.
        prof = await db.execute(select(Profile).where(Profile.user_id == user.id))
        profile = prof.scalar_one_or_none()
        if profile is None or profile.structured_data is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Complete onboarding (upload CV + answer questions) before adding jobs.",
            )

        job = Job(
            user_id=user.id,
            title=title or "Untitled role",
            company=company or "Unknown company",
            location=None,
            description_raw=description,
            source_url=url,
            source_type=body.source_type,
            status="saved",
        )
        db.add(job)
        await db.flush()  # assigns job.id before we use it for the score row

        score = await _score_and_persist(job, profile, db, user)

        await db.commit()
        await db.refresh(job)
        await db.refresh(score)
        return _detail_out(job, score)
    except Exception:
        # DB rollback is handled by get_db() teardown on exception.
        # We still need to reverse the entitlement counter — that was
        # committed eagerly by the dep and won't roll back with the
        # session.
        await refund(db, user, "jobs_created")
        raise


@router.post(
    "/from-pdf",
    response_model=JobDetailOut,
    dependencies=[Depends(rate_limit_ai), Depends(entitlement("jobs_created"))],
)
async def create_from_pdf(
    file: UploadFile = File(...),
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> JobDetailOut:
    """Create a job from an uploaded PDF of the description.

    The PDF isn't stored — we extract text in-memory and discard the
    bytes. Title/company are left for the scoring step to infer from
    the text (same behaviour as a paste with no hints).
    """
    try:
        data = await file.read()
        description = extract_pdf_text(data)

        if len(description) < 100:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Couldn't pull enough text from that PDF — it may be an "
                    "image scan or mostly images. Try copy-pasting the "
                    "description instead."
                ),
            )

        prof = await db.execute(select(Profile).where(Profile.user_id == user.id))
        profile = prof.scalar_one_or_none()
        if profile is None or profile.structured_data is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Complete onboarding (upload CV + answer questions) before adding jobs.",
            )

        job = Job(
            user_id=user.id,
            title="Untitled role",
            company="Unknown company",
            location=None,
            description_raw=description,
            source_url=None,
            source_type="pdf",
            status="saved",
        )
        db.add(job)
        await db.flush()

        score = await _score_and_persist(job, profile, db, user)

        await db.commit()
        await db.refresh(job)
        await db.refresh(score)
        return _detail_out(job, score)
    except Exception:
        await refund(db, user, "jobs_created")
        raise


@router.post(
    "/from-extension",
    response_model=JobDetailOut,
    # This route delegates to create_job as a plain function call, which
    # bypasses create_job's own dep chain. So the entitlement dep MUST
    # be declared here — the delegate won't consume a credit on our
    # behalf. Exactly one consume per HTTP request, which is the goal.
    dependencies=[Depends(rate_limit_ai), Depends(entitlement("jobs_created"))],
)
async def create_from_extension(
    body: JobCreateIn,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> JobDetailOut:
    """Thin alias so the browser extension's endpoint is explicit in the
    API surface. Hard-codes source_type = 'extension' regardless of body.

    Refund-on-failure is inherited from create_job's try/except below
    (same user + resource → same counter row), so we don't repeat the
    try/except here.
    """
    body.source_type = "extension"
    return await create_job(body, user, db)


# --- List / get / patch / delete ----------------------------------------


@router.get("", response_model=list[JobListItem])
async def list_jobs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(default=None, description="Search in title or company"),
) -> list[JobListItem]:
    stmt = select(Job).where(Job.user_id == user.id).order_by(Job.created_at.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Job.title.ilike(like)) | (Job.company.ilike(like)))
    rows = (await db.execute(stmt)).scalars().all()

    # Batch-fetch latest scores in one round trip to avoid N+1.
    job_ids = [j.id for j in rows]
    score_rows = []
    if job_ids:
        score_rows = (
            await db.execute(select(JobScore).where(JobScore.job_id.in_(job_ids)))
        ).scalars().all()
    latest: dict[UUID, JobScore] = {}
    for s in score_rows:
        if s.job_id not in latest or s.scored_at > latest[s.job_id].scored_at:
            latest[s.job_id] = s

    return [
        JobListItem(
            id=j.id,
            title=j.title,
            company=j.company,
            location=j.location,
            status=j.status,
            source_type=j.source_type,
            created_at=j.created_at,
            total_score=latest[j.id].total_score if j.id in latest else None,
            salary_raw=j.salary_raw,
        )
        for j in rows
    ]


@router.get("/compare", response_model=CompareOut)
async def compare_jobs(
    ids: list[UUID] = Query(..., alias="id", description="Repeat ?id= per job"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompareOut:
    """Return full details + scores for 2-4 jobs for the compare view.

    Declared BEFORE /jobs/{job_id} so FastAPI matches this path
    literally (otherwise 'compare' is captured as a UUID and fails).
    """
    if not (2 <= len(ids) <= 4):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Compare 2-4 jobs.")
    rows = (
        await db.execute(
            select(Job).where(Job.id.in_(ids), Job.user_id == user.id)
        )
    ).scalars().all()
    if len(rows) != len(ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="One or more jobs not found")

    out = []
    for job in rows:
        score = await _latest_score(job.id, db)
        out.append(_detail_out(job, score))
    return CompareOut(jobs=out)


@router.get("/{job_id}", response_model=JobDetailOut)
async def get_job(
    job_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobDetailOut:
    job = await _own_job(job_id, user, db)
    score = await _latest_score(job.id, db)
    quota = await _job_quota(user, job.id, db)
    return _detail_out(job, score, quota)


@router.patch("/{job_id}", response_model=JobDetailOut)
async def patch_job(
    job_id: UUID,
    body: JobPatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobDetailOut:
    job = await _own_job(job_id, user, db)
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(job, key, value)
    await db.commit()
    await db.refresh(job)
    score = await _latest_score(job.id, db)
    quota = await _job_quota(user, job.id, db)
    return _detail_out(job, score, quota)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_job(
    job_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await _own_job(job_id, user, db)
    await db.delete(job)
    await db.commit()


@router.post(
    "/{job_id}/score",
    response_model=JobDetailOut,
    dependencies=[Depends(rate_limit_ai)],
)
async def rescore_job(
    job_id: UUID,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> JobDetailOut:
    job = await _own_job(job_id, user, db)
    prof = await db.execute(select(Profile).where(Profile.user_id == user.id))
    profile = prof.scalar_one_or_none()
    if profile is None or profile.structured_data is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="No profile to score against."
        )

    score = await _score_and_persist(job, profile, db, user)
    await db.commit()
    await db.refresh(score)
    return _detail_out(job, score)
