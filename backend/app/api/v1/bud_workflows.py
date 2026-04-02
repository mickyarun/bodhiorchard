"""BUD workflow endpoints: tech arch approval, rejection, and reassignment."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.bud import BUDDocument, BUDStatus
from app.models.user import User
from app.repositories.bud import BUDRepository
from app.repositories.bud_timeline import BUDTimelineRepository
from app.schemas.bud import BUDRead, ReassignmentRequest, RejectTechArchRequest

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post(
    "/approve-tech-arch",
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

        from app.models.user import OrgToUser

        manager_result = await db.execute(
            sa_select(User)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(
                OrgToUser.org_id == current_user.org_id,
                OrgToUser.role == UserRole.MANAGER,
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

    # Re-estimate with developer skills now available
    try:
        from app.services.bud_estimation import estimate_bud_dates

        await estimate_bud_dates(
            db,
            current_user.org_id,
            bud,
            trigger="tech_arch_approved",
            actor_id=current_user.id,
            actor_name=current_user.name,
        )
    except Exception:
        logger.warning("estimation_failed_after_approval", bud_id=str(bud.id))

    await db.flush()
    await db.refresh(bud)
    return bud


@router.post(
    "/reject-tech-arch",
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
    "/request-reassignment",
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
