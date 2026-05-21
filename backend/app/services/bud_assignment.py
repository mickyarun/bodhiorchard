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
from dataclasses import dataclass
from typing import Any, Literal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.user import User, UserRole
from app.repositories.bud import BUDRepository
from app.repositories.bud_timeline import BUDTimelineRepository
from app.repositories.user import UserRepository
from app.services.agent_activity_logger import log_agent_activity
from app.services.bud_timeline import record_event

# Single source of truth for the phase→role chain — see app/services/phase_roles.py.
from app.services.phase_roles import PHASE_ROLE_CHAIN
from app.services.todo_assignment import (
    assign_all_todos_to_lead,
    cascade_assignee_to_todos,
)

# NOTE: ``app.services.smart_assignment`` imports ``_TERMINAL_STATUSES`` from
# this module, so the inverse import has to stay function-local to avoid a
# circular import on app startup. Tested by ``tests/services/test_bud_assignment.py``.

logger = structlog.get_logger(__name__)

# Statuses that don't count toward a user's active workload
_TERMINAL_STATUSES = {BUDStatus.CLOSED, BUDStatus.DISCARDED, BUDStatus.PROD}

# Per-role limit on concurrent active BUDs. A candidate with this many
# (or more) active BUDs is excluded — auto-assignment leaves the BUD
# unassigned with an ``all_at_capacity`` warning rather than overloading
# someone further. Tuned by role realities: PMs juggle many; devs work
# deeply on a few; designers + QA sit in between.
#
# ``ORG_OWNER`` is intentionally NOT a key — the owner isn't a working
# role in ``PHASE_ROLE_CHAIN`` either. They can still be assigned
# manually if needed.
MAX_ACTIVE_BUDS_PER_ROLE: dict[UserRole, int] = {
    UserRole.PM: 10,
    UserRole.MANAGER: 8,
    UserRole.DESIGNER: 5,
    UserRole.QA: 5,
    UserRole.TECH_LEAD: 4,
    UserRole.DEVELOPER: 3,
}
_DEFAULT_MAX_ACTIVE_BUDS = 3


def max_active_buds_for(role: UserRole) -> int:
    """Return the active-BUD cap for ``role``, falling back to the default."""
    return MAX_ACTIVE_BUDS_PER_ROLE.get(role, _DEFAULT_MAX_ACTIVE_BUDS)


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
    """Auto-assign a BUD based on the target phase's role chain.

    Flow:
      1. CODE_REVIEW retains the developer from DEVELOPMENT.
      2. Look up the role chain from PHASE_ROLE_CHAIN; phases with no
         chain skip.
      3. Walk the chain in order, fetching active users for each role.
         The first role with at least one candidate wins. If a non-primary
         role wins, ``assignment_via_fallback`` is set on the lifecycle
         events so the banner can show the substitution rather than a
         silent re-routing.
      4. If every role in the chain returns empty, publish a
         ``phase_assigner`` failed event (reason=no_candidates) and
         return — no scoring, no LLM call.
      5. Publish ``phase_assigner`` invoked, then pick winner: smart-match
         for SMART phases, round-robin fallback.
      6. Record timeline events (unassigned old + assigned new) and
         publish ``phase_assigner`` completed event with the winner.

    Returns the new assignee_id, or the previous assignee_id when the
    chain is exhausted (assignment skipped).
    """
    if new_status == BUDStatus.CODE_REVIEW:
        return await _retain_code_review_assignee(
            db, org_id, bud, actor_id=actor_id, actor_name=actor_name
        )

    chain = PHASE_ROLE_CHAIN.get(new_status.value, ())
    if not chain:
        return bud.assignee_id

    primary_role = chain[0]
    phase_value = new_status.value

    # Continuity: prefer the previous assignee for this BUD when the
    # phase has been visited before. Phase-scoped so an earlier phase's
    # assignment (e.g. PM during BUD phase) doesn't bleed into a later
    # phase's first visit (e.g. DESIGN with PM as the fallback role).
    # Skipped when the previous assignee is inactive, no longer holds
    # an eligible role, over their cap, or was explicitly unassigned
    # afterwards — see _previous_assignee_for_phase.
    continuity = await _previous_assignee_for_phase(db, org_id, bud.id, chain, phase_value)
    if continuity is not None:
        return await _assign_via_continuity(
            db,
            org_id,
            bud,
            pick=continuity,
            phase_value=phase_value,
            new_status=new_status,
            actor_id=actor_id,
            actor_name=actor_name,
        )

    outcome = await _resolve_via_chain(db, org_id, chain)

    if outcome.reason == "no_candidates":
        logger.info(
            "auto_assign_no_candidates",
            role=primary_role.value,
            org_id=str(org_id),
            bud_id=str(bud.id),
            chain=[r.value for r in chain],
        )
        await log_agent_activity(
            db,
            org_id=org_id,
            event_type="skill_failed",
            skill_slug=_PHASE_ASSIGNER_SLUG,
            message=(f"No active {primary_role.value} in this org — assignment skipped"),
            bud_id=bud.id,
            bud_number=bud.bud_number,
            bud_title=bud.title,
            metadata_={
                "reason": "no_candidates",
                # ``role`` is the primary-role contract the frontend banner
                # uses; ``primary_role`` mirrors it explicitly so future
                # callers don't have to know that role IS the primary.
                "role": primary_role.value,
                "primary_role": primary_role.value,
                "phase": phase_value,
                "chain": [r.value for r in chain],
            },
        )
        return await _clear_stale_assignment(
            db, org_id, bud, actor_id=actor_id, actor_name=actor_name
        )

    if outcome.reason == "all_at_capacity":
        assert outcome.over_cap_role is not None  # narrowed by reason
        # Post-rewrite, at_capacity fires only when the PRIMARY role is
        # full (fallback-at-cap continues the walk). The metadata always
        # reports the primary regardless — that's the frontend contract.
        logger.info(
            "auto_assign_all_at_capacity",
            role=primary_role.value,
            org_id=str(org_id),
            bud_id=str(bud.id),
            count=outcome.over_cap_count,
            cap=outcome.over_cap_limit,
        )
        await log_agent_activity(
            db,
            org_id=org_id,
            event_type="skill_failed",
            skill_slug=_PHASE_ASSIGNER_SLUG,
            message=(
                f"All {primary_role.value}s are at capacity "
                f"({outcome.over_cap_limit} active BUDs each) — assignment skipped"
            ),
            bud_id=bud.id,
            bud_number=bud.bud_number,
            bud_title=bud.title,
            metadata_={
                "reason": "all_at_capacity",
                "role": primary_role.value,
                "primary_role": primary_role.value,
                "phase": phase_value,
                "capacity": outcome.over_cap_limit,
                "count": outcome.over_cap_count,
            },
        )
        return await _clear_stale_assignment(
            db, org_id, bud, actor_id=actor_id, actor_name=actor_name
        )

    # outcome.reason == "ok" — narrow types for downstream use.
    candidates = outcome.candidates
    role_name = outcome.role
    assert role_name is not None  # narrowed by reason="ok"
    load_map = outcome.load_map

    via_fallback = role_name != primary_role
    invoked_metadata: dict[str, Any] = {"role": role_name.value, "phase": phase_value}
    if via_fallback:
        invoked_metadata["assignment_via_fallback"] = True
        invoked_metadata["fallback_from"] = primary_role.value
        invoked_metadata["fallback_to"] = role_name.value

    await log_agent_activity(
        db,
        org_id=org_id,
        event_type="skill_invoked",
        skill_slug=_PHASE_ASSIGNER_SLUG,
        message=(
            f"No active {primary_role.value} — assigning {role_name.value} instead…"
            if via_fallback
            else f"Assigning {role_name.value}…"
        ),
        bud_id=bud.id,
        bud_number=bud.bud_number,
        bud_title=bud.title,
        metadata_=invoked_metadata,
    )

    chosen: User | None = None
    method = ""
    if new_status in _SMART_ASSIGNMENT_PHASES:
        # Inline import: see module-header NOTE on the circular dep.
        from app.services.smart_assignment import assign_best_for_role

        try:
            chosen = await assign_best_for_role(
                db,
                org_id,
                bud,
                role=role_name,
                candidates=candidates,
                load_map=load_map,
            )
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
                    "role": role_name.value,
                    "phase": phase_value,
                },
            )
            return bud.assignee_id
        if chosen is not None:
            method = "smart_assignment"

    if chosen is None:
        chosen = _pick_by_round_robin(candidates, load_map)
        method = "auto_round_robin"

    await _record_assignment(
        db,
        org_id=org_id,
        bud=bud,
        chosen=chosen,
        role_name=role_name,
        method=method,
        phase_value=phase_value,
        actor_id=actor_id,
        actor_name=actor_name,
    )

    completed_metadata: dict[str, Any] = {
        "assignee_id": str(chosen.id),
        "assignee_name": chosen.name,
        "role": role_name.value,
        "method": method,
        "phase": phase_value,
    }
    if via_fallback:
        completed_metadata["assignment_via_fallback"] = True
        completed_metadata["fallback_from"] = primary_role.value
        completed_metadata["fallback_to"] = role_name.value

    await log_agent_activity(
        db,
        org_id=org_id,
        event_type="skill_completed",
        skill_slug=_PHASE_ASSIGNER_SLUG,
        message=(
            f"No active {primary_role.value} — assigned {chosen.name} "
            f"({role_name.value}, {method})"
            if via_fallback
            else f"Assigned {chosen.name} ({role_name.value}, {method})"
        ),
        bud_id=bud.id,
        bud_number=bud.bud_number,
        bud_title=bud.title,
        metadata_=completed_metadata,
    )

    logger.info(
        "bud_assigned",
        bud_id=str(bud.id),
        assignee_id=str(chosen.id),
        assignee_name=chosen.name,
        role=role_name.value,
        method=method,
    )
    await _assign_todos_to_lead_if_development(db, org_id, bud.id, new_status, chosen.id)
    return chosen.id


@dataclass(frozen=True)
class _ChainOutcome:
    """Result of walking the phase-role chain with capacity-aware filtering.

    ``reason`` discriminates between three terminal states:

    - ``"ok"`` — at least one role had under-cap candidates; pick from
      ``candidates`` (already filtered to those below the cap).
    - ``"all_at_capacity"`` — at least one role had members but every
      single one is over their cap. ``over_cap_role`` / ``over_cap_count`` /
      ``over_cap_limit`` describe the first such role for the banner.
      The handler emits a warning and leaves the BUD unassigned.
    - ``"no_candidates"`` — no role in the chain had any active members.
      Genuine org-config gap; needs admin to fill the role.
    """

    candidates: list[User]
    load_map: dict[uuid.UUID, int]
    role: UserRole | None
    is_fallback: bool
    reason: Literal["ok", "all_at_capacity", "no_candidates"]
    over_cap_role: UserRole | None = None
    over_cap_count: int = 0
    over_cap_limit: int = 0


async def _resolve_via_chain(
    db: AsyncSession,
    org_id: uuid.UUID,
    chain: tuple[UserRole, ...],
) -> _ChainOutcome:
    """Walk the chain; pick the first role with under-cap members.

    Decision matrix (the "primary role" is ``chain[0]``):

    ============================  =========================  ==========================
    Primary state                 Fallback state             Outcome
    ============================  =========================  ==========================
    has under-cap members         —                          ``ok`` (assign primary)
    members all at cap            —                          ``all_at_capacity`` (STOP)
    zero members                  fallback under-cap         ``ok`` (assign via fallback)
    zero members                  fallback at-cap, deeper    keep walking until
                                  under-cap                  under-cap found OR exhausted
    zero members                  every fallback empty/full  ``no_candidates`` (primary)
    ============================  =========================  ==========================

    Key rule the user explicitly asked for: when the PRIMARY role is
    missing entirely, surface that as the cause even if a fallback was
    at capacity. The fallback being busy is secondary news — the org
    just doesn't have the canonical role filled.
    """
    user_repo = UserRepository(db)
    bud_repo = BUDRepository(db, org_id=org_id)
    primary_role = chain[0]

    for role in chain:
        candidates = await user_repo.list_active_with_role(org_id, role)
        if not candidates:
            continue  # no members for this role; try next

        load_map = await bud_repo.count_active_loads_for_assignees(
            [c.id for c in candidates], [s.value for s in _TERMINAL_STATUSES]
        )
        cap = max_active_buds_for(role)
        under_cap = [c for c in candidates if load_map.get(c.id, 0) < cap]

        if under_cap:
            return _ChainOutcome(
                candidates=under_cap,
                load_map=load_map,
                role=role,
                is_fallback=role != primary_role,
                reason="ok",
            )

        # All members of this role are at cap.
        if role == primary_role:
            # Primary role exists but is fully loaded — STOP. Don't
            # silently route to a fallback while the canonical owners
            # are slammed; the admin needs to see the workload issue.
            return _ChainOutcome(
                candidates=[],
                load_map={},
                role=primary_role,
                is_fallback=False,
                reason="all_at_capacity",
                over_cap_role=primary_role,
                over_cap_count=len(candidates),
                over_cap_limit=cap,
            )

        # Fallback role at cap. Keep walking — the primary is missing
        # (otherwise we wouldn't be on a fallback), so the underlying
        # cause stays "no primary"; the fallback being busy is noise.

    # Chain exhausted without finding under-cap candidates. The
    # primary was either missing entirely or every fallback was busy
    # — either way the user-facing cause is the missing primary.
    return _ChainOutcome(
        candidates=[],
        load_map={},
        role=primary_role,
        is_fallback=False,
        reason="no_candidates",
    )


@dataclass(frozen=True)
class _ContinuityPick:
    """The previous assignee + the role they held when previously assigned.

    Returned by :func:`_previous_assignee_for_phase` so the lifecycle
    event can record which earlier role this continuity decision
    inherits from (rendered as "carried over from previous <phase>"
    on the timeline UI).
    """

    user: User
    role: UserRole
    previous_role: UserRole


async def _assign_via_continuity(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    *,
    pick: "_ContinuityPick",
    phase_value: str,
    new_status: BUDStatus,
    actor_id: uuid.UUID | None,
    actor_name: str | None,
) -> uuid.UUID:
    """Record a continuity-based assignment and emit lifecycle events.

    Same shape as the normal smart-assignment success path: a
    ``skill_invoked`` (so the workflow banner spawns the "AI working…"
    spinner the same way) followed by ``skill_completed``. The
    ``method="continuity"`` + ``continuity_from_role`` metadata lets
    the timeline UI render "carried over from previous <role>".
    """
    method = "continuity"
    common_meta: dict[str, Any] = {
        "role": pick.role.value,
        "method": method,
        "phase": phase_value,
        "continuity_from_role": pick.previous_role.value,
    }

    # invoked first → matches the spinner spawn pattern the workflow
    # banner uses for every other assignment path.
    await log_agent_activity(
        db,
        org_id=org_id,
        event_type="skill_invoked",
        skill_slug=_PHASE_ASSIGNER_SLUG,
        message=f"Reassigning {pick.user.name} (continuity)…",
        bud_id=bud.id,
        bud_number=bud.bud_number,
        bud_title=bud.title,
        metadata_=common_meta,
    )

    await _record_assignment(
        db,
        org_id=org_id,
        bud=bud,
        chosen=pick.user,
        role_name=pick.role,
        method=method,
        phase_value=phase_value,
        actor_id=actor_id,
        actor_name=actor_name,
    )

    await log_agent_activity(
        db,
        org_id=org_id,
        event_type="skill_completed",
        skill_slug=_PHASE_ASSIGNER_SLUG,
        message=(
            f"Reassigned {pick.user.name} ({pick.role.value}) — carried over from "
            f"previous {pick.previous_role.value}"
        ),
        bud_id=bud.id,
        bud_number=bud.bud_number,
        bud_title=bud.title,
        metadata_={
            **common_meta,
            "assignee_id": str(pick.user.id),
            "assignee_name": pick.user.name,
        },
    )
    logger.info(
        "bud_assigned",
        bud_id=str(bud.id),
        assignee_id=str(pick.user.id),
        assignee_name=pick.user.name,
        role=pick.role.value,
        method=method,
        continuity_from_role=pick.previous_role.value,
    )
    await _assign_todos_to_lead_if_development(db, org_id, bud.id, new_status, pick.user.id)
    return pick.user.id


async def _previous_assignee_for_phase(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    chain: tuple[UserRole, ...],
    phase_value: str,
) -> _ContinuityPick | None:
    """Return the previous assignee from the LAST visit to ``phase_value``.

    Continuity rules (in order):

    1. Most recent ``assigned`` event on this BUD with ``detail.phase``
       equal to ``phase_value``. Scoping by phase (rather than by any
       role appearing in ``chain``) stops a previous phase's primary
       role from winning continuity on first entry to a new phase that
       happens to list it as a fallback.
    2. If a user-triggered ``unassigned`` event occurred AFTER that
       assignment (i.e. ``detail.reason != 'auto_assign_skipped'``),
       respect the unassign — return None.
    3. Validate the user is still ``is_active=True`` and still holds an
       eligible role (in ``chain``) in this org.
    4. Validate they're under their role's active-BUD cap.

    Any check failing → return None; the caller falls back to the
    normal chain walk.
    """
    timeline_repo = BUDTimelineRepository(db, org_id=org_id)
    latest = await timeline_repo.latest_assignee_for_phase(bud_id, phase_value)
    if latest is None:
        return None
    prev_user_id, assigned_at, prev_role_str = latest

    # Was the prior assignee deliberately removed afterwards?
    if await timeline_repo.latest_user_unassign_after(bud_id, assigned_at):
        return None

    user = await db.get(User, prev_user_id)
    if user is None or not user.is_active:
        return None

    # Confirm they still hold an eligible role in this org. Re-running
    # the chain's own membership lookup keeps the SCOPE_TYPE rules
    # (system vs custom + base_role) in one place — and means a member
    # whose custom role got deleted is correctly excluded.
    user_repo = UserRepository(db)
    eligible_role: UserRole | None = None
    for role in chain:
        members = await user_repo.list_active_with_role(org_id, role)
        if any(m.id == user.id for m in members):
            eligible_role = role
            break
    if eligible_role is None:
        return None

    # Capacity check: capacity wins over continuity.
    cap = max_active_buds_for(eligible_role)
    bud_repo = BUDRepository(db, org_id=org_id)
    load_map = await bud_repo.count_active_loads_for_assignees(
        [user.id], [s.value for s in _TERMINAL_STATUSES]
    )
    if load_map.get(user.id, 0) >= cap:
        return None

    # The previous-phase role is recorded for the timeline UI's "carried
    # over from previous <role>" banner. Legacy events without a role —
    # or with an unrecognised value — degrade to the eligible role we
    # just resolved rather than dropping continuity entirely.
    previous_role = eligible_role
    if prev_role_str:
        try:
            previous_role = UserRole(prev_role_str)
        except ValueError:
            logger.info(
                "continuity_unknown_prev_role",
                bud_id=str(bud_id),
                prev_role=prev_role_str,
            )

    return _ContinuityPick(user=user, role=eligible_role, previous_role=previous_role)


async def _clear_stale_assignment(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    *,
    actor_id: uuid.UUID | None,
    actor_name: str | None,
) -> uuid.UUID | None:
    """Unassign the BUD when auto-assignment can't pick someone valid.

    Triggered by ``no_candidates`` and ``all_at_capacity`` outcomes:
    keeping the previous assignee in place would mask the warning the
    banner shows (the user clearly expects the avatar to clear when
    the system says "assignment skipped"). No-op when the BUD is
    already unassigned — avoids emitting a noisy timeline event.
    """
    if bud.assignee_id is None:
        return None
    old_id = bud.assignee_id
    bud.assignee_id = None
    await record_event(
        db,
        org_id,
        bud.id,
        "unassigned",
        actor_id=actor_id,
        actor_name=actor_name,
        detail={
            "previous_assignee_id": str(old_id),
            "reason": "auto_assign_skipped",
        },
    )
    return None


async def _retain_code_review_assignee(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    *,
    actor_id: uuid.UUID | None,
    actor_name: str | None,
) -> uuid.UUID | None:
    """CODE_REVIEW keeps the developer from DEVELOPMENT; record it on the timeline.

    Resolves the assignee's actual role rather than hard-coding DEVELOPER
    — DEVELOPMENT can fall back to TECH_LEAD when the dev pool is empty,
    and mis-labelling that as ``developer`` would also corrupt continuity
    on later phase re-entries that look for the real role.
    """
    if not bud.assignee_id:
        return bud.assignee_id
    assignee = await db.get(User, bud.assignee_id)
    actual_role = await UserRepository(db).get_role(bud.assignee_id, org_id)
    detail: dict[str, Any] = {
        "assignee_id": str(bud.assignee_id),
        "assignee_name": assignee.name if assignee else None,
        "method": "retained_from_development",
        "phase": BUDStatus.CODE_REVIEW.value,
    }
    if actual_role is not None:
        detail["role"] = actual_role.value
    await record_event(
        db,
        org_id,
        bud.id,
        "assigned",
        actor_id=actor_id,
        actor_name=actor_name,
        detail=detail,
    )
    return bud.assignee_id


def _pick_by_round_robin(
    candidates: list[User],
    load_map: dict[uuid.UUID, int],
) -> User:
    """Lowest active-BUD load wins; ties broken by earliest created_at.

    The chain resolver already fetched ``load_map`` for cap filtering, so
    we reuse it here instead of re-querying.
    """
    return min(candidates, key=lambda u: (load_map.get(u.id, 0), u.created_at))


async def _record_assignment(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    bud: BUDDocument,
    chosen: User,
    role_name: UserRole,
    method: str,
    phase_value: str,
    actor_id: uuid.UUID | None,
    actor_name: str | None,
) -> None:
    """Write unassigned (if re-assigning) + assigned timeline events.

    ``phase_value`` is stamped onto the ``assigned`` event detail so
    continuity lookups on phase re-entry can match by phase instead of
    by role-in-chain — see ``_previous_assignee_for_phase``.
    """
    old_assignee_id = bud.assignee_id
    if old_assignee_id and old_assignee_id != chosen.id:
        await record_event(
            db,
            org_id,
            bud.id,
            "unassigned",
            actor_id=actor_id,
            actor_name=actor_name,
            # Mark as a system-side reassignment so the continuity-suppression
            # helper (``latest_user_unassign_after``) doesn't treat this as a
            # human "remove this person" signal. Without the marker, every
            # auto-reassignment silently disables continuity for this BUD.
            detail={"previous_assignee_id": str(old_assignee_id), "reason": "reassigned"},
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
            "role": role_name.value,
            "method": method,
            "phase": phase_value,
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
    # Record the assignee's current role too, so continuity lookups on
    # phase re-entry can match this manual event. Falls back to None
    # when the role can't be resolved (legacy data, no membership row).
    user_role = await UserRepository(db).get_role(assignee_id, org_id)
    detail: dict[str, Any] = {
        "assignee_id": str(assignee_id),
        "assignee_name": assignee.name if assignee else None,
        "method": "manual",
        "phase": bud.status.value,
    }
    if user_role is not None:
        detail["role"] = user_role.value
    await record_event(
        db,
        org_id,
        bud.id,
        "assigned",
        actor_id=actor_id,
        actor_name=actor_name,
        detail=detail,
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
