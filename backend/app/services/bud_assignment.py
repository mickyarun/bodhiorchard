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
from app.services.agent_activity_logger import PHASE_ASSIGNER_SLUG, log_agent_activity
from app.services.assignment_policy import (
    BUD_PRIORITY_WEIGHTS,
    MAX_ACTIVE_BUDS_PER_ROLE,
    TERMINAL_BUD_STATUSES,
    max_active_buds_for,
)
from app.services.bud_assignment_actions import assign_bud, unassign_bud
from app.services.bud_timeline import record_event

# Single source of truth for the phase→role chain — see app/services/phase_roles.py.
from app.services.phase_roles import PHASE_ROLE_CHAIN
from app.services.smart_assignment import assign_best_for_role
from app.services.team_scope import (
    TeamScopeResult,
    filter_candidates_by_team_ownership,
    user_is_in_owning_team,
)
from app.services.todo_assignment import (
    assign_todos_per_repo_team,
)
from app.services.yield_offer_lock import supersede_offers_for_assigned_bud
from app.services.yield_offer_service import maybe_raise_yield_offer

# Re-export for callers (and tests) that still patch this attribute name.
__all__ = [
    "BUDStatus",
    "MAX_ACTIVE_BUDS_PER_ROLE",
    "assign_bud",
    "auto_assign_for_phase",
    "max_active_buds_for",
    "unassign_bud",
]

logger = structlog.get_logger(__name__)


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
_PHASE_ASSIGNER_SLUG = PHASE_ASSIGNER_SLUG


def _team_scope_metadata(outcome: "_ChainOutcome") -> dict[str, Any]:
    """Build the team-scope subset of lifecycle-event metadata.

    Always emits ``team_scope_applied`` so absence-of-keys vs
    negative-presence is disambiguable on dashboards. ``fell_back``
    explicitly differentiates "team owns the repo, pick was scoped"
    from "no team owns the repo (or no role match in any owning
    team), fell back to org-wide". ``input_malformed`` flags the
    case where the BUD's ``impacted_repos`` JSONB was non-empty but
    every entry parsed badly — the banner should surface this as a
    data-quality warning even though scoping wasn't applied.
    """
    meta: dict[str, Any] = {
        "team_scope_applied": outcome.team_scope_applied,
    }
    if outcome.team_scope_applied:
        meta["team_scope_fell_back"] = outcome.team_scope_fell_back
        meta["team_scope_impacted_repo_count"] = outcome.team_scope_impacted_repo_count
        meta["team_scope_pool_size"] = outcome.team_scope_pool_size
    if outcome.team_scope_input_malformed:
        meta["team_scope_input_malformed"] = True
    if outcome.team_scope_discarded_count > 0:
        meta["team_scope_discarded_count"] = outcome.team_scope_discarded_count
    return meta


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
    continuity = await _previous_assignee_for_phase(
        db, org_id, bud.id, chain, phase_value, bud.impacted_repos
    )
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

    outcome = await _resolve_via_chain(db, org_id, chain, bud.impacted_repos)

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
                **_team_scope_metadata(outcome),
            },
        )
        return await _clear_stale_assignment(
            db, org_id, bud, actor_id=actor_id, actor_name=actor_name
        )

    if outcome.reason == "all_at_capacity":
        assert outcome.over_cap_role is not None  # narrowed by reason
        # Before declaring failure, try to raise a yield offer. If a
        # saturated candidate is holding a strictly lower-priority BUD,
        # the service writes a YieldOffer row + publishes an event; the
        # developer's Accept/Reject is what actually moves assignment
        # forward. Returning None here keeps the BUD unassigned for now
        # — same as the old behaviour, but with a pending offer in play.
        offer = await maybe_raise_yield_offer(
            db,
            org_id=org_id,
            incoming_bud=bud,
            saturated_candidates=list(outcome.saturated_candidates),
        )
        if offer is not None:
            await log_agent_activity(
                db,
                org_id=org_id,
                event_type="skill_invoked",
                skill_slug=_PHASE_ASSIGNER_SLUG,
                message=(
                    f"All {primary_role.value}s at capacity — yield offer "
                    f"sent for a lower-priority BUD"
                ),
                bud_id=bud.id,
                bud_number=bud.bud_number,
                bud_title=bud.title,
                metadata_={
                    "reason": "yield_offer_pending",
                    "role": primary_role.value,
                    "phase": phase_value,
                    "offer_id": str(offer.id),
                    **_team_scope_metadata(outcome),
                },
            )
            return await _clear_stale_assignment(
                db, org_id, bud, actor_id=actor_id, actor_name=actor_name
            )

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
                **_team_scope_metadata(outcome),
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
    invoked_metadata: dict[str, Any] = {
        "role": role_name.value,
        "phase": phase_value,
        **_team_scope_metadata(outcome),
    }
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
        try:
            chosen = await assign_best_for_role(
                db,
                org_id,
                bud,
                role=role_name,
                candidates=candidates,
                load_map=outcome.weighted_load_map,
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
        extra_detail=_team_scope_metadata(outcome),
    )

    completed_metadata: dict[str, Any] = {
        "assignee_id": str(chosen.id),
        "assignee_name": chosen.name,
        "role": role_name.value,
        "method": method,
        "phase": phase_value,
        **_team_scope_metadata(outcome),
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

    ``team_scope_*`` fields capture whether the candidate pool was
    narrowed by repo-team ownership. Surfaced on the lifecycle banner
    so an admin can see whether the pick was team-scoped or fell back
    to the whole org because no team owns the impacted repo.
    """

    candidates: list[User]
    load_map: dict[uuid.UUID, int]
    # Priority-weighted variant of ``load_map`` for skill-based scoring.
    # Round-robin still uses the count-based ``load_map`` because that
    # matches its "least loaded by raw count" semantics.
    weighted_load_map: dict[uuid.UUID, int]
    role: UserRole | None
    is_fallback: bool
    reason: Literal["ok", "all_at_capacity", "no_candidates"]
    over_cap_role: UserRole | None = None
    over_cap_count: int = 0
    over_cap_limit: int = 0
    # When ``reason == "all_at_capacity"``, this carries the saturated
    # candidate list so the yield-offer service can try displacing a
    # lower-priority BUD. Empty in every other branch.
    saturated_candidates: tuple[User, ...] = ()
    # Team-scope provenance for the eventually-chosen candidate set.
    team_scope_applied: bool = False
    team_scope_fell_back: bool = False
    team_scope_impacted_repo_count: int = 0
    team_scope_pool_size: int = 0
    # Data-quality flags surfaced when the BUD's ``impacted_repos``
    # JSONB had entries that didn't parse — so a corrupted list
    # masquerading as a confident scoping decision is visible.
    team_scope_input_malformed: bool = False
    team_scope_discarded_count: int = 0


async def _resolve_via_chain(
    db: AsyncSession,
    org_id: uuid.UUID,
    chain: tuple[UserRole, ...],
    impacted_repos: list[Any] | None = None,
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
        role_pool = await user_repo.list_active_with_role(org_id, role)
        if not role_pool:
            continue  # no members for this role; try next

        # Team-scope filter: narrows the role pool to members of teams
        # that own one of the BUD's impacted repos. Returns the
        # unfiltered pool with ``fell_back=True`` when no team owns the
        # impacted repos OR when no team member matches this role, so
        # assignment never stalls just because team configuration is
        # incomplete — the banner still flags the gap.
        scope_result: TeamScopeResult = await filter_candidates_by_team_ownership(
            db, org_id, role_pool, impacted_repos
        )
        candidates = scope_result.candidates

        load_map = await bud_repo.count_active_loads_for_assignees(
            [c.id for c in candidates], [s.value for s in TERMINAL_BUD_STATUSES]
        )
        cap = max_active_buds_for(role)
        under_cap = [c for c in candidates if load_map.get(c.id, 0) < cap]

        if under_cap:
            # Second query: priority-weighted load for the under-cap
            # subset only. Used by ``assign_best_for_role`` so candidates
            # holding lower-priority work get preferred over those
            # already loaded with P0/P1s, while the cap stays count-based.
            weighted_load_map = await bud_repo.weighted_active_loads_for_assignees(
                [c.id for c in under_cap],
                [s.value for s in TERMINAL_BUD_STATUSES],
                weights=BUD_PRIORITY_WEIGHTS,
            )
            return _ChainOutcome(
                candidates=under_cap,
                load_map=load_map,
                weighted_load_map=weighted_load_map,
                role=role,
                is_fallback=role != primary_role,
                reason="ok",
                team_scope_applied=scope_result.applied,
                team_scope_fell_back=scope_result.fell_back,
                team_scope_impacted_repo_count=scope_result.impacted_repo_count,
                team_scope_pool_size=scope_result.team_pool_size,
                team_scope_input_malformed=scope_result.input_malformed,
                team_scope_discarded_count=scope_result.discarded_count,
            )

        # All members of this role are at cap.
        if role == primary_role:
            # Primary role exists but is fully loaded — STOP. Don't
            # silently route to a fallback while the canonical owners
            # are slammed; the admin needs to see the workload issue.
            return _ChainOutcome(
                candidates=[],
                load_map={},
                weighted_load_map={},
                role=primary_role,
                is_fallback=False,
                reason="all_at_capacity",
                over_cap_role=primary_role,
                over_cap_count=len(candidates),
                over_cap_limit=cap,
                saturated_candidates=tuple(candidates),
                team_scope_applied=scope_result.applied,
                team_scope_fell_back=scope_result.fell_back,
                team_scope_impacted_repo_count=scope_result.impacted_repo_count,
                team_scope_pool_size=scope_result.team_pool_size,
                team_scope_input_malformed=scope_result.input_malformed,
                team_scope_discarded_count=scope_result.discarded_count,
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
        weighted_load_map={},
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
    impacted_repos: list[Any] | None = None,
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
    5. When the BUD has impacted repos, validate the user is still in
       a team that owns at least one — staleness here (user removed
       from the owning team between visits) breaks the team-scope
       invariant the rest of the picker enforces.

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
        [user.id], [s.value for s in TERMINAL_BUD_STATUSES]
    )
    if load_map.get(user.id, 0) >= cap:
        return None

    # Team-scope freshness: when the BUD has impacted repos, the
    # continuity user MUST still own at least one of them. Without
    # this check, removing a developer from the team they previously
    # delivered for would silently re-route the next phase back to
    # them on continuity — the exact staleness team-scoping was
    # added to prevent.
    if impacted_repos and not await user_is_in_owning_team(db, org_id, user.id, impacted_repos):
        logger.info(
            "continuity_user_no_longer_in_owning_team",
            bud_id=str(bud_id),
            user_id=str(user.id),
            role=eligible_role.value,
        )
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
    extra_detail: dict[str, Any] | None = None,
) -> None:
    """Write unassigned (if re-assigning) + assigned timeline events.

    ``phase_value`` is stamped onto the ``assigned`` event detail so
    continuity lookups on phase re-entry can match by phase instead of
    by role-in-chain — see ``_previous_assignee_for_phase``.

    ``extra_detail`` is merged into the ``assigned`` event detail —
    used by the chain-resolver path to stamp ``team_scope_*`` keys so
    the BUD timeline UI can render "from <Team>" or "fell back to
    org-wide" without re-querying the team tables.
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
    # Any offer still asking somebody to yield for this BUD is now moot.
    await supersede_offers_for_assigned_bud(db, org_id, bud.id)
    detail: dict[str, Any] = {
        "assignee_id": str(chosen.id),
        "assignee_name": chosen.name,
        "role": role_name.value,
        "method": method,
        "phase": phase_value,
    }
    if extra_detail:
        # ``extra_detail`` is for provenance addenda (team scope,
        # capacity context, etc.) — never for overriding who/what was
        # assigned. A colliding key would silently corrupt the audit
        # trail (timeline UI and XP/SP metrics read these keys), so
        # fail loud in tests rather than ship a split-brain record.
        overlap = set(extra_detail) & set(detail)
        if overlap:
            raise ValueError(
                "_record_assignment extra_detail must not collide with core "
                f"detail keys: {sorted(overlap)}"
            )
        detail.update(extra_detail)
    await record_event(
        db,
        org_id,
        bud.id,
        "assigned",
        actor_id=actor_id,
        actor_name=actor_name,
        detail=detail,
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
        await assign_todos_per_repo_team(db, org_id, bud_id, lead_user_id)
    except Exception:
        logger.warning("todo_lead_assignment_failed", bud_id=str(bud_id))


# ``assign_bud`` / ``unassign_bud`` were extracted to
# ``app.services.bud_assignment_actions`` so the yield-offer service
# can call them without a cycle. Re-exported here for callers that
# still import from this module.
