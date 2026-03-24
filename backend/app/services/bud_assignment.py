"""Auto-assignment service for BUD lifecycle phases.

Assigns BUDs to team members based on the target phase's role,
using least-loaded (round-robin) balancing across active members.
"""

import uuid

import structlog
from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.user import User, UserRole
from app.services.bud_timeline import record_event

logger = structlog.get_logger(__name__)

# Maps each lifecycle phase to the UserRole responsible for it.
# Phases not listed here (PROD, CLOSED, DISCARDED) skip auto-assignment.
PHASE_ROLE_MAP: dict[BUDStatus, str] = {
    BUDStatus.BUD: UserRole.PM,
    BUDStatus.DESIGN: UserRole.DESIGNER,
    BUDStatus.TECH_ARCH: UserRole.TECH_LEAD,
    BUDStatus.DEVELOPMENT: UserRole.DEVELOPER,
    BUDStatus.TESTING: UserRole.QA,
    BUDStatus.UAT: UserRole.PM,
}

# Statuses that don't count toward a user's active workload
_TERMINAL_STATUSES = {BUDStatus.CLOSED, BUDStatus.DISCARDED, BUDStatus.PROD}


async def auto_assign_for_phase(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    new_status: BUDStatus,
    actor_id: uuid.UUID | None = None,
    actor_name: str | None = None,
) -> uuid.UUID | None:
    """Auto-assign a BUD based on the target phase's role.

    1. Look up role name from PHASE_ROLE_MAP
    2. Find active users with that role in this org
    3. Pick the user with fewest active BUDs assigned (ties: earliest created_at)
    4. Update bud.assignee_id
    5. Record timeline events (unassigned old + assigned new)

    Returns new assignee_id, or None if no matching members.
    """
    role_name = PHASE_ROLE_MAP.get(new_status)
    if role_name is None:
        return bud.assignee_id

    # Smart assignment for DEVELOPMENT phase: use skill-based matching
    if new_status == BUDStatus.DEVELOPMENT:
        from app.services.smart_assignment import assign_best_developer

        chosen_user = await assign_best_developer(db, org_id, bud)
        if chosen_user:
            old_assignee_id = bud.assignee_id
            if old_assignee_id and old_assignee_id != chosen_user.id:
                await record_event(
                    db,
                    org_id,
                    bud.id,
                    "unassigned",
                    actor_id=actor_id,
                    actor_name=actor_name,
                    detail={"previous_assignee_id": str(old_assignee_id)},
                )
            bud.assignee_id = chosen_user.id
            await record_event(
                db,
                org_id,
                bud.id,
                "assigned",
                actor_id=actor_id,
                actor_name=actor_name,
                detail={
                    "assignee_id": str(chosen_user.id),
                    "assignee_name": chosen_user.name,
                    "role": role_name,
                    "method": "smart_assignment",
                },
            )
            logger.info(
                "bud_smart_assigned",
                bud_id=str(bud.id),
                assignee_id=str(chosen_user.id),
                assignee_name=chosen_user.name,
            )
            return chosen_user.id
        # Fall through to round-robin if smart assignment returns None

    # Find active users with the target role
    from app.models.user import OrgToUser

    result = await db.execute(
        select(User)
        .join(OrgToUser, OrgToUser.user_id == User.id)
        .where(
            OrgToUser.org_id == org_id,
            OrgToUser.role == role_name,
            User.is_active == true(),
        )
    )
    candidates = list(result.scalars().all())

    if not candidates:
        logger.info(
            "auto_assign_no_candidates",
            role=role_name,
            org_id=str(org_id),
            bud_id=str(bud.id),
        )
        return bud.assignee_id

    candidate_ids = [c.id for c in candidates]

    # Count active BUDs per candidate
    load_result = await db.execute(
        select(BUDDocument.assignee_id, func.count())
        .where(
            BUDDocument.org_id == org_id,
            BUDDocument.assignee_id.in_(candidate_ids),
            BUDDocument.status.notin_([s.value for s in _TERMINAL_STATUSES]),
        )
        .group_by(BUDDocument.assignee_id)
    )
    load_map: dict[uuid.UUID, int] = {row[0]: row[1] for row in load_result}

    # Pick lowest load; ties broken by earliest created_at
    candidates.sort(key=lambda u: (load_map.get(u.id, 0), u.created_at))
    chosen = candidates[0]

    # Record unassign event if changing assignee
    old_assignee_id = bud.assignee_id
    if old_assignee_id and old_assignee_id != chosen.id:
        await record_event(
            db,
            org_id,
            bud.id,
            "unassigned",
            actor_id=actor_id,
            actor_name=actor_name,
            detail={"previous_assignee_id": str(old_assignee_id)},
        )

    # Assign
    bud.assignee_id = chosen.id
    await record_event(
        db,
        org_id,
        bud.id,
        "assigned",
        actor_id=actor_id,
        actor_name=actor_name,
        detail={
            "assignee_id": str(chosen.id),
            "assignee_name": chosen.name,
            "role": role_name,
            "method": "auto_round_robin",
        },
    )

    logger.info(
        "bud_auto_assigned",
        bud_id=str(bud.id),
        assignee_id=str(chosen.id),
        assignee_name=chosen.name,
        role=role_name,
    )

    return chosen.id


async def assign_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    assignee_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    actor_name: str | None,
) -> None:
    """Manually assign a BUD. Records timeline event."""
    assignee = await db.get(User, assignee_id)
    bud.assignee_id = assignee_id
    await record_event(
        db,
        org_id,
        bud.id,
        "assigned",
        actor_id=actor_id,
        actor_name=actor_name,
        detail={
            "assignee_id": str(assignee_id),
            "assignee_name": assignee.name if assignee else None,
            "method": "manual",
        },
    )


async def unassign_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    actor_id: uuid.UUID | None,
    actor_name: str | None,
) -> None:
    """Remove assignment from a BUD. Records timeline event."""
    old_id = bud.assignee_id
    bud.assignee_id = None
    await record_event(
        db,
        org_id,
        bud.id,
        "unassigned",
        actor_id=actor_id,
        actor_name=actor_name,
        detail={"previous_assignee_id": str(old_id) if old_id else None},
    )
