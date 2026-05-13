# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
from app.services.agent_activity_logger import log_agent_activity
from app.services.bud_timeline import record_event
from app.services.todo_assignment import (
    assign_all_todos_to_lead,
    cascade_assignee_to_todos,
)

# NOTE: ``app.services.smart_assignment`` imports ``_TERMINAL_STATUSES`` from
# this module, so the inverse import has to stay function-local to avoid a
# circular import on app startup. Tested by ``tests/services/test_bud_assignment.py``.

logger = structlog.get_logger(__name__)

# Maps each lifecycle phase to the UserRole responsible for it.
# Phases not listed here (PROD, CLOSED, DISCARDED) skip auto-assignment.
# The UAT entry is only reachable when the org has UAT enabled in
# org.config.bud_stages (see app.services.org_settings.is_uat_enabled) —
# UAT-disabled orgs never transition to BUDStatus.UAT, so auto_assign_for_phase
# will never look this key up for them. Keeping it in the map is harmless
# and avoids per-org map filtering.
PHASE_ROLE_MAP: dict[BUDStatus, UserRole] = {
    BUDStatus.BUD: UserRole.PM,
    BUDStatus.DESIGN: UserRole.DESIGNER,
    BUDStatus.TECH_ARCH: UserRole.TECH_LEAD,
    BUDStatus.DEVELOPMENT: UserRole.DEVELOPER,
    BUDStatus.TESTING: UserRole.QA,
    BUDStatus.UAT: UserRole.PM,
}

# Statuses that don't count toward a user's active workload
_TERMINAL_STATUSES = {BUDStatus.CLOSED, BUDStatus.DISCARDED, BUDStatus.PROD}

# Phases that use smart (skill-based) assignment instead of round-robin.
# Extended to all role-mapped phases so Design/PM/Tech-Arch also benefit
# from skill matching; smart picker falls back to round-robin when the
# top score is ambiguous, so this is a strict superset of the old behaviour.
_SMART_ASSIGNMENT_PHASES = {
    BUDStatus.BUD,
    BUDStatus.DESIGN,
    BUDStatus.TECH_ARCH,
    BUDStatus.DEVELOPMENT,
    BUDStatus.TESTING,
}

# Skill slug used for lifecycle events emitted by this service.
_PHASE_ASSIGNER_SLUG = "phase_assigner"


async def auto_assign_for_phase(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    new_status: BUDStatus,
    actor_id: uuid.UUID | None = None,
    actor_name: str | None = None,
) -> uuid.UUID | None:
    """Auto-assign a BUD based on the target phase's role.

    Flow:
      1. CODE_REVIEW retains the developer from DEVELOPMENT.
      2. Look up role from PHASE_ROLE_MAP; phases with no mapping skip.
      3. Fetch active users for that role. If empty, publish a
         ``phase_assigner`` failed event (reason=no_candidates) and
         return — no scoring, no LLM call.
      4. Publish ``phase_assigner`` invoked (banner shows "Assigning …").
      5. Pick winner: smart-match for SMART phases, round-robin fallback.
      6. Record timeline events (unassigned old + assigned new) and
         publish ``phase_assigner`` completed event with the winner.

    Returns the new assignee_id, or the previous assignee_id when the
    role pool is empty (assignment skipped).
    """
    if new_status == BUDStatus.CODE_REVIEW:
        return await _retain_code_review_assignee(
            db, org_id, bud, actor_id=actor_id, actor_name=actor_name
        )

    role_name = PHASE_ROLE_MAP.get(new_status)
    if role_name is None:
        return bud.assignee_id

    # Fetch the candidate pool exactly once. Empty pool short-circuits
    # before any LLM-capable code path is reached.
    candidates = await UserRepository(db).list_active_with_role(org_id, role_name)
    phase_value = new_status.value
    if not candidates:
        logger.info(
            "auto_assign_no_candidates",
            role=role_name,
            org_id=str(org_id),
            bud_id=str(bud.id),
        )
        await log_agent_activity(
            db,
            org_id=org_id,
            event_type="skill_failed",
            skill_slug=_PHASE_ASSIGNER_SLUG,
            message=f"No active {role_name} in this org — assignment skipped",
            bud_id=bud.id,
            bud_number=bud.bud_number,
            bud_title=bud.title,
            metadata_={
                "reason": "no_candidates",
                "role": role_name,
                "phase": phase_value,
            },
        )
        return bud.assignee_id

    await log_agent_activity(
        db,
        org_id=org_id,
        event_type="skill_invoked",
        skill_slug=_PHASE_ASSIGNER_SLUG,
        message=f"Assigning {role_name}…",
        bud_id=bud.id,
        bud_number=bud.bud_number,
        bud_title=bud.title,
        metadata_={"role": role_name, "phase": phase_value},
    )

    chosen: User | None = None
    method = ""
    if new_status in _SMART_ASSIGNMENT_PHASES:
        # Inline import: see module-header NOTE on the circular dep.
        from app.services.smart_assignment import assign_best_for_role

        try:
            chosen = await assign_best_for_role(db, org_id, bud, role=role_name)
        except Exception as exc:
            # Smart picker can raise on LLM-tiebreak crash, DB hiccup, etc.
            # Without this guard the ``skill_invoked`` row above is orphaned
            # (banner stuck) AND the caller sees a 500. Emit a terminal
            # lifecycle event so the user sees the actual error, then fall
            # through to round-robin so assignment still has a chance.
            logger.warning("smart_assignment_failed", bud_id=str(bud.id), error=str(exc))
            await log_agent_activity(
                db,
                org_id=org_id,
                event_type="skill_failed",
                skill_slug=_PHASE_ASSIGNER_SLUG,
                message=f"Skill-based assignment failed: {exc}",
                bud_id=bud.id,
                bud_number=bud.bud_number,
                bud_title=bud.title,
                metadata_={
                    "reason": "smart_assignment_error",
                    "role": role_name,
                    "phase": phase_value,
                },
            )
            return bud.assignee_id
        if chosen is not None:
            method = "smart_assignment"

    if chosen is None:
        chosen = await _pick_by_round_robin(db, org_id, candidates)
        method = "auto_round_robin"

    await _record_assignment(
        db,
        org_id=org_id,
        bud=bud,
        chosen=chosen,
        role_name=role_name,
        method=method,
        actor_id=actor_id,
        actor_name=actor_name,
    )

    await log_agent_activity(
        db,
        org_id=org_id,
        event_type="skill_completed",
        skill_slug=_PHASE_ASSIGNER_SLUG,
        message=f"Assigned {chosen.name} ({role_name}, {method})",
        bud_id=bud.id,
        bud_number=bud.bud_number,
        bud_title=bud.title,
        metadata_={
            "assignee_id": str(chosen.id),
            "assignee_name": chosen.name,
            "role": role_name,
            "method": method,
            "phase": phase_value,
        },
    )

    logger.info(
        "bud_assigned",
        bud_id=str(bud.id),
        assignee_id=str(chosen.id),
        assignee_name=chosen.name,
        role=role_name,
        method=method,
    )
    await _assign_todos_to_lead_if_development(db, org_id, bud.id, new_status, chosen.id)
    return chosen.id


async def _retain_code_review_assignee(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    *,
    actor_id: uuid.UUID | None,
    actor_name: str | None,
) -> uuid.UUID | None:
    """CODE_REVIEW keeps the developer from DEVELOPMENT; record it on the timeline."""
    if not bud.assignee_id:
        return bud.assignee_id
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


async def _pick_by_round_robin(
    db: AsyncSession,
    org_id: uuid.UUID,
    candidates: list[User],
) -> User:
    """Lowest active-BUD load wins; ties broken by earliest created_at."""
    candidate_ids = [c.id for c in candidates]
    load_map = await BUDRepository(db, org_id=org_id).count_active_loads_for_assignees(
        candidate_ids, [s.value for s in _TERMINAL_STATUSES]
    )
    candidates.sort(key=lambda u: (load_map.get(u.id, 0), u.created_at))
    return candidates[0]


async def _record_assignment(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    bud: BUDDocument,
    chosen: User,
    role_name: UserRole,
    method: str,
    actor_id: uuid.UUID | None,
    actor_name: str | None,
) -> None:
    """Write unassigned (if re-assigning) + assigned timeline events."""
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
            "method": method,
        },
    )


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
    """Manually assign a BUD. Records timeline event.

    During DEVELOPMENT, also cascades the new assignee onto every
    non-checkpoint TODO — UNLESS any TODO is already in_progress,
    completed, or has been taken over via ``takeover_todo``. In that
    case the cascade is skipped to preserve developer claims, and the
    top-level reassignment still goes through for visibility.
    """
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

    if bud.status == BUDStatus.DEVELOPMENT:
        # The cascade returns -1 (and is a no-op) when any TODO has been
        # claimed or progressed — no exception, so no try/except needed.
        # A genuine DB error must propagate so the outer transaction rolls
        # back; silently logging would leave the BUD assignee changed but
        # the TODOs stale, which is worse than failing the whole request.
        await cascade_assignee_to_todos(db, org_id, bud.id, assignee_id)


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
