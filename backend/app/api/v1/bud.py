"""BUD CRUD endpoints."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.bud import BUDDesignStatus, BUDDocument, BUDStatus, BUDTimelineEvent
from app.models.user import User
from app.repositories.bud import BUDChatMessageRepository, BUDDesignRepository, BUDRepository
from app.repositories.bud_timeline import BUDTimelineRepository
from app.schemas.bud import (
    EXPORTABLE_SECTIONS,
    SECTION_PATTERN,
    BUDCreate,
    BUDDesignRead,
    BUDListItem,
    BUDRead,
    BUDUpdate,
    ChatMessageRead,
    DesignGenerateRequest,
    DesignHtmlUpdate,
    ReassignmentRequest,
    RejectTechArchRequest,
    TimelineEventRead,
)
from app.schemas.jobs import (
    ChatJobPayload,
    CodeReviewJobPayload,
    DesignAgentJobPayload,
    JobCreatedResponse,
    TechArchJobPayload,
)
from app.services.job_queue import (
    JOB_BUD_CHAT,
    JOB_CODE_REVIEW,
    JOB_DESIGN_AGENT,
    JOB_TECH_ARCH,
    create_job,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["buds"])


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

    for field, value in update_data.items():
        setattr(bud, field, value)

    await db.flush()
    await db.refresh(bud)

    logger.info("bud_updated", bud_id=str(bud.id), fields=list(update_data.keys()))

    if (
        "status" in update_data
        and update_data["status"] == BUDStatus.DESIGN
        and old_status != BUDStatus.DESIGN
    ):
        response.headers["X-Design-Available"] = "true"

    # ── Code review transition: DEVELOPMENT → CODE_REVIEW ──────────
    if (
        "status" in update_data
        and update_data["status"] == BUDStatus.CODE_REVIEW
        and old_status != BUDStatus.CODE_REVIEW
    ):
        # Read confirmed_repos from metadata (set by frontend before transition)
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

    if (
        "status" in update_data
        and update_data["status"] == BUDStatus.TECH_ARCH
        and old_status != BUDStatus.TECH_ARCH
    ):
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
        # Store job ID so frontend can resume tracking on remount
        meta = dict(bud.metadata_ or {})
        meta["tech_arch_job_id"] = tech_arch_job.job_id
        bud.metadata_ = meta
        await db.flush()
        await db.refresh(bud)
        response.headers["X-TechArch-Job"] = "true"

    return bud


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


# ── Tech Architecture Approval ────────────────────────────────────


@router.post(
    "/{bud_id}/approve-tech-arch",
    response_model=BUDRead,
    dependencies=[Depends(require_permissions("buds:approve"))],
)
async def approve_tech_arch(
    bud_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDDocument:
    """Approve a BUD's tech architecture plan.

    Tech leads approve first; if a manager exists, they must also approve
    before the BUD transitions to DEVELOPMENT.
    """
    from app.models.user import UserRole
    from app.services.bud_assignment import auto_assign_for_phase
    from app.services.bud_timeline import record_event
    from app.services.notification_service import send_lifecycle_notification

    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    if bud.status != BUDStatus.TECH_ARCH:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"BUD is in '{bud.status}' status, not 'tech_arch'",
        )

    approver_role = current_user.role
    if approver_role not in (UserRole.TECH_LEAD, UserRole.MANAGER, UserRole.ORG_OWNER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only tech leads, managers, or org owners can approve",
        )

    meta = dict(bud.metadata_ or {})
    approval_state = meta.get("tech_arch_approval", {})

    # If tech_lead approving, check if manager exists
    if approver_role == UserRole.TECH_LEAD:
        from sqlalchemy import select as sa_select

        manager_result = await db.execute(
            sa_select(User)
            .where(
                User.org_id == current_user.org_id,
                User.role == UserRole.MANAGER,
                User.is_active == True,  # noqa: E712
            )
            .limit(1)
        )
        manager_user = manager_result.scalar_one_or_none()

        if manager_user is not None:
            # Partial approval — store state, notify manager
            import datetime as _dt

            approval_state["tech_lead_id"] = str(current_user.id)
            approval_state["tech_lead_at"] = _dt.datetime.now(_dt.UTC).isoformat()
            approval_state["awaiting_manager"] = True
            meta["tech_arch_approval"] = approval_state
            bud.metadata_ = meta

            await record_event(
                db,
                current_user.org_id,
                bud.id,
                "tech_arch_approved",
                actor_id=current_user.id,
                actor_name=current_user.name,
                detail={
                    "approved_by": str(current_user.id),
                    "level": "tech_lead",
                    "awaiting_manager": True,
                },
            )

            bud_ref = f"BUD-{bud.bud_number:03d}"
            send_lifecycle_notification(
                org_id=str(current_user.org_id),
                user_id=str(manager_user.id),
                notification_type="approval_requested",
                title=f"Manager approval needed: {bud_ref}",
                message=(
                    f"Tech lead {current_user.name} approved the tech plan for "
                    f'"{bud.title}". Your approval is needed to proceed.'
                ),
                bud_id=str(bud.id),
            )

            await db.flush()
            await db.refresh(bud)
            return bud

    # Full approval — transition to DEVELOPMENT
    await record_event(
        db,
        current_user.org_id,
        bud.id,
        "tech_arch_approved",
        actor_id=current_user.id,
        actor_name=current_user.name,
        detail={
            "approved_by": str(current_user.id),
            "level": approver_role.value,
            "final": True,
        },
    )

    # Clear approval state
    meta.pop("tech_arch_approval", None)
    bud.metadata_ = meta

    # Transition to DEVELOPMENT
    bud.status = BUDStatus.DEVELOPMENT

    await record_event(
        db,
        current_user.org_id,
        bud.id,
        "status_change",
        actor_id=current_user.id,
        actor_name=current_user.name,
        detail={"from": BUDStatus.TECH_ARCH.value, "to": BUDStatus.DEVELOPMENT.value},
    )

    # Smart assignment for development
    new_assignee_id = await auto_assign_for_phase(
        db,
        current_user.org_id,
        bud,
        BUDStatus.DEVELOPMENT,
        actor_id=current_user.id,
        actor_name=current_user.name,
    )

    # Notify newly assigned developer
    if new_assignee_id:
        bud_ref = f"BUD-{bud.bud_number:03d}"
        send_lifecycle_notification(
            org_id=str(current_user.org_id),
            user_id=str(new_assignee_id),
            notification_type="developer_assigned",
            title=f"You've been assigned: {bud_ref}",
            message=f'You\'ve been assigned to implement "{bud.title}".',
            bud_id=str(bud.id),
        )

    await db.flush()
    await db.refresh(bud)
    return bud


@router.post(
    "/{bud_id}/reject-tech-arch",
    response_model=BUDRead,
    dependencies=[Depends(require_permissions("buds:approve"))],
)
async def reject_tech_arch(
    bud_id: uuid.UUID,
    body: RejectTechArchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDDocument:
    """Reject a BUD's tech architecture plan with a reason."""
    from app.services.bud_timeline import record_event
    from app.services.notification_service import send_lifecycle_notification

    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    if bud.status != BUDStatus.TECH_ARCH:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"BUD is in '{bud.status}' status, not 'tech_arch'",
        )

    await record_event(
        db,
        current_user.org_id,
        bud.id,
        "tech_arch_rejected",
        actor_id=current_user.id,
        actor_name=current_user.name,
        detail={"rejected_by": str(current_user.id), "reason": body.reason},
    )

    # Clear any partial approval state
    meta = dict(bud.metadata_ or {})
    meta.pop("tech_arch_approval", None)
    bud.metadata_ = meta

    # Find BUD creator to notify (first timeline event actor)
    timeline_repo = BUDTimelineRepository(db, org_id=current_user.org_id)
    events = await timeline_repo.list_for_bud(bud_id)
    creator_id = None
    for evt in events:
        if evt.event_type == "created" and evt.actor_id:
            creator_id = evt.actor_id
            break

    if creator_id:
        bud_ref = f"BUD-{bud.bud_number:03d}"
        send_lifecycle_notification(
            org_id=str(current_user.org_id),
            user_id=str(creator_id),
            notification_type="approval_rejected",
            title=f"Tech plan rejected: {bud_ref}",
            message=f"Reason: {body.reason[:200]}",
            bud_id=str(bud.id),
        )

    await db.flush()
    await db.refresh(bud)
    return bud


@router.post(
    "/{bud_id}/request-reassignment",
    response_model=BUDRead,
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def request_reassignment(
    bud_id: uuid.UUID,
    body: ReassignmentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDDocument:
    """Request reassignment of a BUD during DEVELOPMENT phase."""
    from app.services.bud_timeline import record_event
    from app.services.notification_service import send_lifecycle_notification
    from app.services.smart_assignment import reassign_developer

    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    if bud.status != BUDStatus.DEVELOPMENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reassignment is only allowed during development",
        )

    if bud.assignee_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the current assignee can request reassignment",
        )

    await record_event(
        db,
        current_user.org_id,
        bud.id,
        "reassignment_requested",
        actor_id=current_user.id,
        actor_name=current_user.name,
        detail={"requested_by": str(current_user.id), "reason": body.reason},
    )

    new_dev = await reassign_developer(
        db,
        current_user.org_id,
        bud,
        current_user.id,
        body.reason,
    )

    if new_dev:
        # Unassign old
        await record_event(
            db,
            current_user.org_id,
            bud.id,
            "unassigned",
            actor_id=current_user.id,
            actor_name=current_user.name,
            detail={"previous_assignee_id": str(current_user.id)},
        )
        # Assign new
        bud.assignee_id = new_dev.id
        await record_event(
            db,
            current_user.org_id,
            bud.id,
            "assigned",
            actor_id=current_user.id,
            actor_name=current_user.name,
            detail={
                "assignee_id": str(new_dev.id),
                "assignee_name": new_dev.name,
                "role": "developer",
                "method": "reassignment",
            },
        )

        bud_ref = f"BUD-{bud.bud_number:03d}"
        send_lifecycle_notification(
            org_id=str(current_user.org_id),
            user_id=str(new_dev.id),
            notification_type="reassignment_done",
            title=f"Reassigned to you: {bud_ref}",
            message=(
                f'You\'ve been assigned to "{bud.title}" (reassigned from {current_user.name}).'
            ),
            bud_id=str(bud.id),
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No eligible developer found for reassignment",
        )

    await db.flush()
    await db.refresh(bud)
    return bud


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


# ── Design wireframes ─────────────────────────────────────────────


@router.get(
    "/{bud_id}/designs",
    response_model=list[BUDDesignRead],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def list_designs(
    bud_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List all design wireframes for a BUD with repo names."""
    design_repo = BUDDesignRepository(db, org_id=current_user.org_id)
    return await design_repo.list_with_repo_names(bud_id)


@router.post(
    "/{bud_id}/designs/generate",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def generate_designs(
    bud_id: uuid.UUID,
    body: DesignGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Create bud_design rows and enqueue design jobs for each repo."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    design_repo = BUDDesignRepository(db, org_id=current_user.org_id)
    repo_ids: list[uuid.UUID | None] = list(body.repo_ids) if body.repo_ids else [None]

    design_rows: list[tuple[uuid.UUID | None, str]] = []
    for rid in repo_ids:
        design = await design_repo.upsert(
            bud_id=bud.id,
            repo_id=rid,
            status=BUDDesignStatus.PENDING,
        )
        design_rows.append((rid, str(design.id)))
    await db.flush()

    results = []
    for rid, design_id in design_rows:
        payload = DesignAgentJobPayload(
            org_id=str(current_user.org_id),
            bud_id=str(bud.id),
            bud_number=bud.bud_number,
            title=bud.title,
            requirements_md=bud.requirements_md or "",
            repo_id=str(rid) if rid else None,
            design_id=design_id,
        )
        job = create_job(
            JOB_DESIGN_AGENT,
            payload=payload.model_dump(),
            user_id=str(current_user.id),
        )

        design_obj = await design_repo.get_by_id(uuid.UUID(design_id))
        if design_obj:
            design_obj.job_id = job.job_id
            design_obj.status = BUDDesignStatus.GENERATING

        results.append(
            {
                "designId": design_id,
                "repoId": str(rid) if rid else None,
                "jobId": job.job_id,
            }
        )
        logger.info(
            "design_job_created",
            bud_id=str(bud.id),
            repo_id=str(rid) if rid else None,
            job_id=job.job_id,
            design_id=design_id,
        )

    await db.flush()
    return results


@router.put(
    "/{bud_id}/designs/{design_id}",
    response_model=BUDDesignRead,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def update_design_html(
    bud_id: uuid.UUID,
    design_id: uuid.UUID,
    body: DesignHtmlUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually edit a design wireframe's HTML or notes."""
    design_repo = BUDDesignRepository(db, org_id=current_user.org_id)
    design = await design_repo.get_by_id(design_id)
    if design is None or design.bud_id != bud_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design not found")

    if body.design_html is not None:
        from app.services.html_sanitizer import sanitize_design_html

        design.design_html = sanitize_design_html(body.design_html)
        design.status = BUDDesignStatus.READY
    if body.notes is not None:
        design.notes = body.notes
    await db.flush()
    await db.refresh(design)

    designs = await design_repo.list_with_repo_names(bud_id)
    return next((d for d in designs if d["id"] == design_id), designs[0])


@router.post(
    "/{bud_id}/designs/{design_id}/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def regenerate_design(
    bud_id: uuid.UUID,
    design_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Re-trigger design generation for a single design."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    design_repo = BUDDesignRepository(db, org_id=current_user.org_id)
    design = await design_repo.get_by_id(design_id)
    if design is None or design.bud_id != bud_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design not found")

    design.status = BUDDesignStatus.GENERATING
    await db.flush()

    payload = DesignAgentJobPayload(
        org_id=str(current_user.org_id),
        bud_id=str(bud.id),
        bud_number=bud.bud_number,
        title=bud.title,
        requirements_md=bud.requirements_md or "",
        repo_id=str(design.repo_id) if design.repo_id else None,
        design_id=str(design.id),
    )
    job = create_job(
        JOB_DESIGN_AGENT,
        payload=payload.model_dump(),
        user_id=str(current_user.id),
    )

    design.job_id = job.job_id
    await db.flush()

    return {"designId": str(design.id), "jobId": job.job_id}


# ── Chat history + Chat ───────────────────────────────────────────


@router.get(
    "/{bud_id}/chat-history",
    response_model=list[ChatMessageRead],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_chat_history(
    bud_id: uuid.UUID,
    section: str = Query("requirements_md"),
    design_id: uuid.UUID | None = Query(None),
    session_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Load persisted chat messages for a BUD section (and optional design/session)."""
    chat_repo = BUDChatMessageRepository(db, org_id=current_user.org_id)
    messages = await chat_repo.list_messages(bud_id, section, design_id, session_id)
    return [
        {
            "id": m.id,
            "role": m.role,
            "message": m.message,
            "user_id": m.user_id,
            "session_id": m.session_id,
            "user_name": m.user.name if m.user else None,
            "created_at": m.created_at,
        }
        for m in messages
    ]


class BUDChatRequest(BaseModel):
    """Schema for a chat message about a BUD's content."""

    message: str = Field(..., min_length=1, max_length=5000)
    section: str = Field(
        "requirements_md",
        pattern=SECTION_PATTERN,
    )
    design_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    images: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Base64 data-URL images pasted from clipboard (max 3)",
    )


@router.post(
    "/{bud_id}/chat",
    response_model=JobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def chat_bud(
    bud_id: uuid.UUID,
    body: BUDChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobCreatedResponse:
    """Submit a BUD chat request for async AI processing."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    # Resolve current content — for design, use bud_designs table
    design_repo_id: str | None = None
    if body.section == "design":
        current_content = ""
        if body.design_id:
            design_repo = BUDDesignRepository(db, org_id=current_user.org_id)
            design = await design_repo.get_by_id(body.design_id)
            if design:
                design_repo_id = str(design.repo_id) if design.repo_id else None
                if design.design_html:
                    current_content = design.design_html
        if not current_content:
            design_repo = BUDDesignRepository(db, org_id=current_user.org_id)
            all_designs = await design_repo.list_for_bud(bud_id)
            for d in all_designs:
                if d.status == BUDDesignStatus.READY and d.design_html:
                    current_content = d.design_html
                    if not design_repo_id and d.repo_id:
                        design_repo_id = str(d.repo_id)
                    break
    else:
        current_content = getattr(bud, body.section) or ""

    # Persist user message to chat history
    chat_repo = BUDChatMessageRepository(db, org_id=current_user.org_id)
    await chat_repo.add_message(
        bud_id=bud.id,
        section=body.section,
        role="user",
        message=body.message,
        design_id=body.design_id,
        user_id=current_user.id,
        session_id=body.session_id,
    )
    await db.flush()

    payload = ChatJobPayload(
        bud_id=str(bud.id),
        org_id=str(current_user.org_id),
        bud_number=bud.bud_number,
        section=body.section,
        current_content=current_content,
        title=bud.title,
        message=body.message,
        design_id=str(body.design_id) if body.design_id else None,
        repo_id=design_repo_id,
        user_id=str(current_user.id),
        session_id=str(body.session_id) if body.session_id else None,
        images=body.images,
    )

    job = create_job(JOB_BUD_CHAT, payload=payload.model_dump(), user_id=str(current_user.id))
    return JobCreatedResponse(job_id=job.job_id)


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
