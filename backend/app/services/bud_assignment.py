# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Auto-assignment service for BUD lifecycle phases.

Assigns BUDs to team members based on the target phase's role,
using least-loaded (round-robin) balancing across active members.
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.user import User, UserRole
from app.repositories.bud import BUDRepository
from app.repositories.user import UserRepository
from app.services.bud_timeline import record_event

logger = structlog.get_logger(__name__)

# Maps each lifecycle phase to the UserRole responsible for it.
# Phases not listed here (PROD, CLOSED, DISCARDED) skip auto-assignment.
# The UAT entry is only reachable when the org has UAT enabled in
# org.config.bud_stages (see app.services.org_settings.is_uat_enabled) —
# UAT-disabled orgs never transition to BUDStatus.UAT, so auto_assign_for_phase
# will never look this key up for them. Keeping it in the map is harmless
# and avoids per-org map filtering.
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

# Phases that use smart (skill-based) assignment instead of round-robin
_SMART_ASSIGNMENT_PHASES = {BUDStatus.DEVELOPMENT, BUDStatus.TESTING}


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
    # Code review stays with the developer who built the feature. No
    # reassignment — the current assignee is already the most recent
    # developer from the development phase. Record a timeline event so
    # the assignment is visible in the BUD's history.
    if new_status == BUDStatus.CODE_REVIEW:
        if bud.assignee_id:
            assignee = await db.get(User, bud.assignee_id)
            await record_event(
                db,
                org_id,
                bud.id,
                "assigned",
                actor_id=actor_id,
                actor_name=actor_name,
                detail={
                    "assignee_id": str(bud.assignee_id),
                    "assignee_name": assignee.name if assignee else None,
                    "role": UserRole.DEVELOPER,
                    "method": "retained_from_development",
                },
            )
        return bud.assignee_id

    role_name = PHASE_ROLE_MAP.get(new_status)
    if role_name is None:
        return bud.assignee_id

    # Smart assignment for phases that benefit from skill-based matching
    if new_status in _SMART_ASSIGNMENT_PHASES:
        from app.services.smart_assignment import assign_best_for_role

        chosen_user = await assign_best_for_role(db, org_id, bud, role=role_name)
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
            await _assign_todos_to_lead_if_development(
                db, org_id, bud.id, new_status, chosen_user.id
            )
            return chosen_user.id
        # Fall through to round-robin if smart assignment returns None

    # Find active users with the target role
    candidates = await UserRepository(db).list_active_with_role(org_id, role_name)

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
    load_map = await BUDRepository(db, org_id=org_id).count_active_loads_for_assignees(
        candidate_ids, [s.value for s in _TERMINAL_STATUSES]
    )

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

    await _assign_todos_to_lead_if_development(db, org_id, bud.id, new_status, chosen.id)
    return chosen.id


async def _assign_todos_to_lead_if_development(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    new_status: BUDStatus,
    lead_user_id: uuid.UUID,
) -> None:
    """Assign all unassigned TODOs to the phase lead on DEVELOPMENT entry.

    Preserves the existing single-owner-per-BUD mental model — one person
    is responsible by default. Other developers can still self-assign
    individual TODOs via the Claim button or MCP ``takeover_todo``.
    Failure is non-fatal — primary assignment still succeeds.
    """
    if new_status != BUDStatus.DEVELOPMENT:
        return
    try:
        from app.services.todo_assignment import assign_all_todos_to_lead

        await assign_all_todos_to_lead(db, org_id, bud_id, lead_user_id)
    except Exception:
        logger.warning("todo_lead_assignment_failed", bud_id=str(bud_id))


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
