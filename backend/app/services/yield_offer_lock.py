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

"""Releasing the phase-assigner lock a yield offer holds.

Raising a yield offer parks ``phase_assigner`` on a ``skill_invoked``
event with no terminal partner, because the assignment chain is
genuinely waiting on a human. Everything that ends that wait has to
release the lock, or the BUD stays ``agentLocked`` in the UI.

Lives in its own module rather than in ``yield_offer_service`` because
``bud_assignment_actions`` needs it too, and that module sits *below*
``yield_offer_service`` in the import graph — ``accept_offer`` calls
``assign_bud``, so the dependency cannot run the other way.
"""

import uuid
from typing import Literal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_activity import AgentActivityLogRepository
from app.repositories.bud import BUDRepository
from app.repositories.yield_offer import YieldOfferRepository
from app.services.agent_activity_logger import PHASE_ASSIGNER_SLUG, log_agent_activity
from app.services.event_bus import publish

logger = structlog.get_logger(__name__)

Resolution = Literal["accepted", "rejected", "expired", "superseded"]


async def close_phase_assigner(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    offer_id: uuid.UUID,
    incoming_bud_id: uuid.UUID,
    resolution: Resolution,
    message: str,
    bud_number: int | None = None,
    bud_title: str | None = None,
) -> None:
    """Emit the terminal ``phase_assigner`` event for a resolved offer.

    ``auto_assign_for_phase`` logs ``skill_invoked`` with
    ``reason=yield_offer_pending`` and returns, so the phase worker stays
    in-flight for as long as the offer is open. ``get_active_phase_worker``
    reads a trailing ``skill_invoked`` as "an agent is running right now",
    which the BUD detail page turns into ``agentLocked`` — disabling the
    entire status menu, Delete, and the AI panel. Without this call the
    only thing that ever cleared that state was
    ``reconcile_orphan_phase_workers`` on the next backend start, so a
    long-lived deployment accumulated permanently frozen BUDs.

    No-ops unless the BUD's newest ``phase_assigner`` event is still the
    ``skill_invoked`` *this* offer parked. A restart-time reconcile (or any
    later assignment run) can close the loop first and let the BUD carry on
    into other phases; emitting unconditionally would then either raise a
    stale "assignment skipped" banner on a BUD that has long since moved
    on, or — if a real phase worker happens to be mid-flight — tear down a
    live progress banner and unlock a BUD while an agent is mutating it.

    Writes on the caller's session and lets failures propagate, so the
    unlock is atomic with the accept/reject/expire that earned it. Catching
    here would be actively harmful: ``log_agent_activity`` flushes, so a
    failed write leaves the session needing rollback, and swallowing it
    just converts a clear error into a ``PendingRollbackError`` at commit —
    or, in the expiry loop, an endpoint that fails identically on every
    retry because the sweep can never commit.
    """
    activity_repo = AgentActivityLogRepository(db, org_id=org_id)
    parked = await activity_repo.get_active_phase_worker(incoming_bud_id, [PHASE_ASSIGNER_SLUG])
    if parked is None or (parked.metadata_ or {}).get("offer_id") != str(offer_id):
        return

    await log_agent_activity(
        db,
        org_id=org_id,
        event_type="skill_completed" if resolution == "accepted" else "skill_failed",
        skill_slug=PHASE_ASSIGNER_SLUG,
        message=message,
        bud_id=incoming_bud_id,
        bud_number=bud_number,
        bud_title=bud_title,
        metadata_={"reason": f"yield_offer_{resolution}"},
    )


async def supersede_offers_for_assigned_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
) -> None:
    """Close out any pending offer whose incoming BUD just got an assignee.

    A yield offer exists to find somebody for a BUD that has nobody. The
    moment that BUD is assigned, the question it asks is already
    answered. Leaving it pending would keep asking the target to give up
    a BUD for work that is no longer theirs to take — and worse, an
    Accept on that dead offer would unassign their current BUD and take
    the incoming one back off whoever now owns it. It would also hold the
    phase-assigner lock, so the whole status menu stays disabled until
    the 24h TTL or the next backend restart.

    Call this from EVERY path that gives a BUD an assignee. Three places
    write ``bud.assignee_id`` to a user and each one calls this:
    ``bud_assignment_actions.assign_bud`` (manual PATCH + accepted
    offer), ``bud_assignment._record_assignment`` (every automated
    phase assignment), and the reassign-developer endpoint in
    ``api/v1/bud_workflows``. There is no single mutation site to hang
    this off, so a new writer must remember — the tests name each caller
    so a missing one fails rather than silently rotting.

    ``accept_offer`` settles its own offer before assigning, so its row
    is no longer pending here and keeps its ``accepted`` status.
    """
    repo = YieldOfferRepository(db, org_id=org_id)
    superseded = await repo.supersede_pending_for_incoming_bud(bud_id)
    if not superseded:
        return
    info = (await BUDRepository(db, org_id=org_id).get_minimal_info_by_ids({bud_id})).get(bud_id)
    for offer_id, target_user_id in superseded:
        logger.info(
            "yield_offer_superseded",
            offer_id=str(offer_id),
            bud_id=str(bud_id),
            target_user_id=str(target_user_id),
        )
        await close_phase_assigner(
            db,
            org_id=org_id,
            offer_id=offer_id,
            incoming_bud_id=bud_id,
            resolution="superseded",
            message="BUD assigned directly — yield offer no longer needed",
            bud_number=int(info["number"]) if info else None,
            bud_title=str(info["title"]) if info else None,
        )
        # Unlike accept/reject/expire, this transition is triggered by
        # somebody else's request, so without a publish the target's board
        # notice keeps the row until they reload — and clicking Accept
        # then 400s on the pending-status guard.
        publish(
            f"yield_offer:{target_user_id}",
            {
                "event": "resolved",
                "offer_id": str(offer_id),
                "org_id": str(org_id),
                "target_user_id": str(target_user_id),
                "resolution": "superseded",
            },
        )
