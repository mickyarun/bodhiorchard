"""BUD CRUD endpoints and sub-router aggregation."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.bud_chat import router as chat_router
from app.api.v1.bud_designs import router as designs_router
from app.api.v1.bud_workflows import router as workflows_router
from app.core.deps import get_current_user, get_db, require_permissions
from app.models.bud import BUDDocument, BUDStatus, BUDTimelineEvent
from app.models.user import User
from app.repositories.bud import BUDRepository
from app.repositories.bud_timeline import BUDTimelineRepository
from app.schemas.bud import (
    EXPORTABLE_SECTIONS,
    BUDCreate,
    BUDListItem,
    BUDRead,
    BUDUpdate,
    TimelineEventRead,
)
from app.schemas.jobs import (
    CodeReviewJobPayload,
    TechArchJobPayload,
)
from app.services.job_queue import (
    JOB_CODE_REVIEW,
    JOB_TECH_ARCH,
    create_job,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["buds"])

# ── Sub-routers ───────────────────────────────────────────────────
router.include_router(designs_router, prefix="/{bud_id}/designs", tags=["bud-designs"])
router.include_router(workflows_router, prefix="/{bud_id}", tags=["bud-workflows"])
router.include_router(chat_router, prefix="/{bud_id}", tags=["bud-chat"])


# ── CRUD ──────────────────────────────────────────────────────────


@router.get(
    "/",
    response_model=list[BUDListItem],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def list_buds(
    status_filter: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BUDDocument]:
    """List BUDs for the current user's organization."""
    if status_filter:
        try:
            BUDStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            ) from None

    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    return await bud_repo.list_buds(status_filter=status_filter)


@router.post(
    "/",
    response_model=BUDRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions("buds:create"))],
)
async def create_bud(
    body: BUDCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDDocument:
    """Create a new BUD with auto-incremented bud_number."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    next_number = await bud_repo.next_bud_number()

    bud = BUDDocument(
        org_id=current_user.org_id,
        bud_number=next_number,
        title=body.title,
        status=BUDStatus.BUD,
        requirements_md=body.requirements_md,
        metadata_=body.metadata_,
    )
    await bud_repo.create(bud)

    from app.services.feature_lifecycle import create_planned_feature

    await create_planned_feature(
        db,
        current_user.org_id,
        next_number,
        body.title,
        body.requirements_md or "",
    )

    # Record timeline + auto-assign
    from app.services.bud_assignment import auto_assign_for_phase
    from app.services.bud_timeline import record_event

    await record_event(
        db,
        current_user.org_id,
        bud.id,
        "created",
        actor_id=current_user.id,
        actor_name=current_user.name,
        detail={"source": "web"},
    )
    await auto_assign_for_phase(
        db,
        current_user.org_id,
        bud,
        BUDStatus.BUD,
        actor_id=current_user.id,
        actor_name=current_user.name,
    )

    logger.info("bud_created", bud_id=str(bud.id), bud_number=next_number, org_id=str(bud.org_id))

    return bud


@router.get(
    "/{bud_id}",
    response_model=BUDRead,
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_bud(
    bud_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDDocument:
    """Retrieve a single BUD by ID."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")
    return bud


@router.get(
    "/{bud_id}/timeline",
    response_model=list[TimelineEventRead],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_bud_timeline(
    bud_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BUDTimelineEvent]:
    """Fetch timeline events for a BUD in chronological order."""
    repo = BUDTimelineRepository(db, org_id=current_user.org_id)
    return await repo.list_for_bud(bud_id)


@router.patch(
    "/{bud_id}",
    response_model=BUDRead,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def update_bud(
    bud_id: uuid.UUID,
    body: BUDUpdate,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDDocument:
    """Update a BUD (title, status, requirements, tech spec, test plan, metadata)."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    update_data = body.model_dump(exclude_unset=True)

    if "status" in update_data:
        try:
            update_data["status"] = BUDStatus(update_data["status"])
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {update_data['status']}",
            ) from None

    if "status" in update_data:
        from app.services.feature_lifecycle import transition_feature_for_bud

        await transition_feature_for_bud(
            db,
            current_user.org_id,
            bud.bud_number,
            update_data["status"],
        )

    # Capture old values BEFORE applying updates
    old_status = bud.status
    old_assignee_id = bud.assignee_id
    old_title = bud.title

    # Handle manual assignee_id changes (before status logic which may auto-assign)
    if "assignee_id" in update_data:
        from app.services.bud_assignment import assign_bud, unassign_bud

        new_aid = update_data.pop("assignee_id")
        if new_aid and new_aid != old_assignee_id:
            await assign_bud(
                db,
                current_user.org_id,
                bud,
                new_aid,
                current_user.id,
                current_user.name,
            )
        elif not new_aid and old_assignee_id:
            await unassign_bud(
                db,
                current_user.org_id,
                bud,
                current_user.id,
                current_user.name,
            )

    # Record status change + auto-assign
    if "status" in update_data:
        new_status = update_data["status"]

        from app.services.bud_assignment import auto_assign_for_phase
        from app.services.bud_timeline import record_event

        await record_event(
            db,
            current_user.org_id,
            bud.id,
            "status_change",
            actor_id=current_user.id,
            actor_name=current_user.name,
            detail={"from": old_status.value, "to": new_status.value},
        )
        await auto_assign_for_phase(
            db,
            current_user.org_id,
            bud,
            new_status,
            actor_id=current_user.id,
            actor_name=current_user.name,
        )

    # Record title change
    if "title" in update_data and update_data["title"] != old_title:
        from app.services.bud_timeline import record_event

        await record_event(
            db,
            current_user.org_id,
            bud.id,
            "content_updated",
            actor_id=current_user.id,
            actor_name=current_user.name,
            detail={"section": "title", "old_title": old_title, "new_title": update_data["title"]},
        )

    for field, value in update_data.items():
        setattr(bud, field, value)

    await db.flush()
    await db.refresh(bud)

    logger.info("bud_updated", bud_id=str(bud.id), fields=list(update_data.keys()))

    # Trigger side-effect jobs on status transitions
    await _trigger_status_jobs(bud, old_status, update_data, response, current_user, db)

    return bud


async def _trigger_status_jobs(
    bud: BUDDocument,
    old_status: BUDStatus,
    update_data: dict,
    response: Response,
    current_user: User,
    db: AsyncSession,
) -> None:
    """Enqueue jobs and set response headers for status transitions.

    Mutates bud.metadata_ and flushes to DB when jobs are created.
    """
    if "status" not in update_data:
        return

    new_status = update_data["status"]

    if new_status == BUDStatus.DESIGN and old_status != BUDStatus.DESIGN:
        response.headers["X-Design-Available"] = "true"

    # Code review transition: DEVELOPMENT → CODE_REVIEW
    if new_status == BUDStatus.CODE_REVIEW and old_status != BUDStatus.CODE_REVIEW:
        meta = dict(bud.metadata_ or {})
        confirmed_repos = meta.get("confirmed_repos", [])

        code_review_payload = CodeReviewJobPayload(
            org_id=str(current_user.org_id),
            bud_id=str(bud.id),
            bud_number=bud.bud_number,
            title=bud.title,
            tech_spec_md=bud.tech_spec_md or "",
            confirmed_repos=confirmed_repos,
        )
        cr_job = create_job(
            JOB_CODE_REVIEW,
            payload=code_review_payload.model_dump(),
            user_id=str(current_user.id),
        )
        meta["code_review_job_id"] = cr_job.job_id
        bud.metadata_ = meta
        await db.flush()
        await db.refresh(bud)
        response.headers["X-CodeReview-Job"] = "true"

    # Tech arch transition
    if new_status == BUDStatus.TECH_ARCH and old_status != BUDStatus.TECH_ARCH:
        payload = TechArchJobPayload(
            org_id=str(current_user.org_id),
            bud_id=str(bud.id),
            bud_number=bud.bud_number,
            title=bud.title,
            requirements_md=bud.requirements_md or "",
        )
        tech_arch_job = create_job(
            JOB_TECH_ARCH, payload=payload.model_dump(), user_id=str(current_user.id)
        )
        meta = dict(bud.metadata_ or {})
        meta["tech_arch_job_id"] = tech_arch_job.job_id
        bud.metadata_ = meta
        await db.flush()
        await db.refresh(bud)
        response.headers["X-TechArch-Job"] = "true"


@router.delete(
    "/{bud_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("backlog:delete"))],
)
async def delete_bud(
    bud_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a BUD."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    from app.services.feature_lifecycle import transition_feature_for_bud

    await transition_feature_for_bud(
        db,
        current_user.org_id,
        bud.bud_number,
        BUDStatus.DISCARDED,
    )

    await bud_repo.delete(bud)
    logger.info("bud_deleted", bud_id=str(bud.id))


# ── Commit tracking ───────────────────────────────────────────────


class CommitRepoRead(BaseModel):
    """Schema for a repo with commit info for a BUD."""

    repo_path: str
    repo_name: str
    commit_count: int
    first_sha: str
    last_sha: str


@router.get(
    "/{bud_id}/commits/repos",
    response_model=list[CommitRepoRead],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def list_commit_repos(
    bud_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CommitRepoRead]:
    """List repos with commits for a BUD, grouped by repo.

    Used by the frontend when transitioning to code_review to show
    a confirmation dialog of which repos have been touched.
    """
    from pathlib import Path

    from app.repositories.bud_commit import BUDCommitRepository

    commit_repo = BUDCommitRepository(db, org_id=current_user.org_id)
    summaries = await commit_repo.list_repos_for_bud(bud_id)

    return [
        CommitRepoRead(
            repo_path=s.repo_path,
            repo_name=Path(s.repo_path).name,
            commit_count=s.commit_count,
            first_sha=s.first_sha,
            last_sha=s.last_sha,
        )
        for s in summaries
    ]


# ── Export / Import ───────────────────────────────────────────────


@router.get(
    "/{bud_id}/export/{section}",
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def export_bud_section(
    bud_id: uuid.UUID,
    section: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """Download a BUD section as a markdown file."""
    if section not in EXPORTABLE_SECTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid section. Must be one of: {', '.join(EXPORTABLE_SECTIONS)}.",
        )

    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    content = getattr(bud, section) or ""
    bud_ref = f"BUD-{bud.bud_number:03d}"
    section_suffix = section.replace("_md", "").replace("_", "-")
    filename = f"{bud_ref}-{section_suffix}.md"

    return PlainTextResponse(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/{bud_id}/import/{section}",
    response_model=BUDRead,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def import_bud_section(
    bud_id: uuid.UUID,
    section: str,
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDDocument:
    """Upload a markdown file to replace a BUD section."""
    if section not in EXPORTABLE_SECTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid section. Must be one of: {', '.join(EXPORTABLE_SECTIONS)}.",
        )

    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    raw = await file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not valid UTF-8. Please save as UTF-8 and try again.",
        ) from None

    if len(content) > 512_000:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum 500KB.",
        )

    setattr(bud, section, content)
    await db.flush()
    await db.refresh(bud)

    logger.info(
        "bud_section_imported",
        bud_id=str(bud.id),
        section=section,
        size=len(content),
    )

    return bud
