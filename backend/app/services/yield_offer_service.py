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

"""Yield-offer create/accept/reject orchestration.

The chain walker in ``bud_assignment`` calls into here when it can't
find an under-capacity candidate for a higher-priority BUD but at least
one assignee is holding something lower-priority. We pick the best
yield candidate, write a ``YieldOffer`` row, and emit an
``yield_offer.created`` event so the dashboard / Slack transports can
deliver it. The developer's Accept/Reject lives in
``api/v1/yield_offers.py``.
"""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.user import User
from app.models.yield_offer import YieldOffer, YieldOfferStatus
from app.repositories.bud import BUDRepository
from app.repositories.yield_offer import YieldOfferRepository
from app.services.assignment_policy import BUD_PRIORITY_WEIGHTS, TERMINAL_BUD_STATUSES
from app.services.bud_assignment_actions import assign_bud, unassign_bud
from app.services.event_bus import publish
from app.services.yield_offer_lock import close_phase_assigner

logger = structlog.get_logger(__name__)

# How long a pending offer survives before it's marked expired on read.
YIELD_OFFER_TTL = timedelta(hours=24)


async def maybe_raise_yield_offer(
    db: AsyncSession,
    org_id: uuid.UUID,
    incoming_bud: BUDDocument,
    saturated_candidates: list[User],
) -> YieldOffer | None:
    """Pick a yield target for a higher-priority BUD and create the offer.

    Called by ``_resolve_via_chain`` when every role member is at cap.
    Scans ``saturated_candidates`` for one currently holding at least
    one BUD strictly lower-priority than ``incoming_bud``; picks the
    candidate whose lowest-priority active BUD has the biggest gap to
    the incoming one (most-yieldable). Returns ``None`` when no
    candidate qualifies — the caller falls through to the existing
    "no_yield_accepted" queue path.

    Idempotent: if a pending offer already exists for this incoming
    BUD, return that row instead of creating a duplicate.
    """
    if not saturated_candidates:
        return None

    repo = YieldOfferRepository(db, org_id=org_id)
    if await repo.has_pending_for_incoming_bud(incoming_bud.id):
        logger.info("yield_offer_already_pending", bud_id=str(incoming_bud.id))
        return None

    yieldable = await _find_best_yield_candidate(db, org_id, incoming_bud, saturated_candidates)
    if yieldable is None:
        return None

    target_user, yieldable_bud = yieldable
    offer = YieldOffer(
        org_id=org_id,
        incoming_bud_id=incoming_bud.id,
        yieldable_bud_id=yieldable_bud.id,
        target_user_id=target_user.id,
        status=YieldOfferStatus.PENDING,
    )
    await repo.create(offer)

    # Per-user topic — WS routing in ``app/api/v1/ws.py`` only allows a
    # client to subscribe to ``yield_offer:{their_own_user_id}``, so
    # this is both the delivery channel and the authorization scope.
    publish(
        f"yield_offer:{target_user.id}",
        {
            "event": "created",
            "offer_id": str(offer.id),
            "org_id": str(org_id),
            "target_user_id": str(target_user.id),
            "incoming_bud_id": str(incoming_bud.id),
            "incoming_bud_priority": incoming_bud.priority.value,
            "yieldable_bud_id": str(yieldable_bud.id),
            "yieldable_bud_priority": yieldable_bud.priority.value,
        },
    )
    logger.info(
        "yield_offer_created",
        offer_id=str(offer.id),
        target=str(target_user.id),
        incoming=str(incoming_bud.id),
        yieldable=str(yieldable_bud.id),
    )
    return offer


async def accept_offer(
    db: AsyncSession,
    org_id: uuid.UUID,
    offer_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    acting_user_name: str | None,
) -> YieldOffer:
    """Accept an offer: release the yieldable BUD, assign the incoming one.

    Routes both BUD mutations through ``assign_bud`` / ``unassign_bud``
    so the timeline records the events, continuity lookups see the new
    assignment on the next phase entry, and the DEVELOPMENT-phase TODO
    cascade fires correctly. Direct ``assignee_id =`` would skip all of
    that.

    Raises:
        ValueError: offer not found, not addressed to the acting user,
            or not in the pending state.
    """
    repo = YieldOfferRepository(db, org_id=org_id)
    offer = await repo.get_by_id(offer_id)
    _guard_actor(offer, acting_user_id, expected_status=YieldOfferStatus.PENDING)
    assert offer is not None  # narrowed by _guard_actor

    bud_repo = BUDRepository(db, org_id=org_id)
    yieldable_bud = await bud_repo.get_by_id(offer.yieldable_bud_id)
    incoming_bud = await bud_repo.get_by_id(offer.incoming_bud_id)
    if yieldable_bud is None or incoming_bud is None:
        raise ValueError("offer references a deleted BUD")

    # Settle this offer BEFORE assigning. ``assign_bud`` supersedes every
    # offer still pending for the BUD it assigns, so an accept that flipped
    # its own status afterwards would first mark itself ``superseded`` and
    # emit the wrong terminal event. Same transaction either way, so a
    # later failure still rolls the status back.
    offer.status = YieldOfferStatus.ACCEPTED
    await db.flush()

    await unassign_bud(
        db,
        org_id,
        yieldable_bud,
        actor_id=acting_user_id,
        actor_name=acting_user_name,
        reason="yielded",
    )
    await assign_bud(
        db,
        org_id,
        incoming_bud,
        acting_user_id,
        actor_id=acting_user_id,
        actor_name=acting_user_name,
        method="yield_offer_accepted",
    )

    await close_phase_assigner(
        db,
        org_id=org_id,
        offer_id=offer.id,
        incoming_bud_id=incoming_bud.id,
        resolution="accepted",
        message=f"Yield offer accepted — assigned to {acting_user_name or 'the developer'}",
        bud_number=incoming_bud.bud_number,
        bud_title=incoming_bud.title,
    )

    publish(
        f"yield_offer:{acting_user_id}",
        {
            "event": "resolved",
            "offer_id": str(offer.id),
            "org_id": str(org_id),
            "target_user_id": str(acting_user_id),
            "resolution": "accepted",
        },
    )
    return offer


async def reject_offer(
    db: AsyncSession,
    org_id: uuid.UUID,
    offer_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> YieldOffer:
    """Reject an offer. Caller may re-run assignment to pick the next candidate."""
    repo = YieldOfferRepository(db, org_id=org_id)
    offer = await repo.get_by_id(offer_id)
    _guard_actor(offer, acting_user_id, expected_status=YieldOfferStatus.PENDING)
    assert offer is not None

    offer.status = YieldOfferStatus.REJECTED
    await db.flush()

    incoming = await BUDRepository(db, org_id=org_id).get_by_id(offer.incoming_bud_id)
    await close_phase_assigner(
        db,
        org_id=org_id,
        offer_id=offer.id,
        incoming_bud_id=offer.incoming_bud_id,
        resolution="rejected",
        message="Yield offer declined — assignment skipped",
        bud_number=incoming.bud_number if incoming else None,
        bud_title=incoming.title if incoming else None,
    )

    publish(
        f"yield_offer:{acting_user_id}",
        {
            "event": "resolved",
            "offer_id": str(offer.id),
            "org_id": str(org_id),
            "target_user_id": str(acting_user_id),
            "resolution": "rejected",
        },
    )
    return offer


async def _expire_overdue_and_unlock(db: AsyncSession, org_id: uuid.UUID) -> None:
    """Run the TTL sweep and close the phase assigner for each expiry.

    Shared by both ``*_with_expiry`` readers so the unlock can never be
    wired into one entry point and forgotten on the other — the failure
    mode this whole change exists to remove.
    """
    repo = YieldOfferRepository(db, org_id=org_id)
    expired = await repo.expire_overdue(older_than=datetime.now(UTC) - YIELD_OFFER_TTL)
    if not expired:
        return
    # Org-scoped lookup: this runs per-request, unlike the cross-tenant
    # startup reconciler, so tenant isolation stays enforced at the
    # repository rather than resting on where the ids came from.
    bud_repo = BUDRepository(db, org_id=org_id)
    bud_info = await bud_repo.get_minimal_info_by_ids({bud_id for _, bud_id in expired})
    for offer_id, bud_id in expired:
        info = bud_info.get(bud_id)
        await close_phase_assigner(
            db,
            org_id=org_id,
            offer_id=offer_id,
            incoming_bud_id=bud_id,
            resolution="expired",
            message="Yield offer expired with no response — assignment skipped",
            bud_number=int(info["number"]) if info else None,
            bud_title=str(info["title"]) if info else None,
        )


async def list_pending_with_expiry(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[YieldOffer]:
    """Run TTL expiry then return pending offers for ``user_id``.

    Single entry point for the board notice + inbox tile — collapses
    "expire stale rows" + "fetch pending" into one call so handlers
    don't have to remember the order.
    """
    await _expire_overdue_and_unlock(db, org_id)
    return await YieldOfferRepository(db, org_id=org_id).list_pending_for_user(user_id)


async def list_org_pending_with_expiry(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> list[YieldOffer]:
    """Admin lens: every pending offer in the org, post-expiry."""
    await _expire_overdue_and_unlock(db, org_id)
    return await YieldOfferRepository(db, org_id=org_id).list_pending_for_org()


async def reassign_offer(
    db: AsyncSession,
    org_id: uuid.UUID,
    offer_id: uuid.UUID,
    new_target_user_id: uuid.UUID,
) -> YieldOffer:
    """Re-route a pending offer to a different developer.

    Admin override (``team:manage``). The new target must currently
    hold at least one BUD strictly lower-priority than the incoming
    BUD — otherwise there's nothing to yield. Updates both
    ``target_user_id`` and ``yieldable_bud_id`` atomically, then
    publishes a ``resolved`` event to the OLD target (so their UI
    removes the row) and a ``created`` event to the NEW target
    (so their UI shows the offer).

    Raises:
        ValueError: offer not pending, or new target has no yieldable BUD.
    """
    repo = YieldOfferRepository(db, org_id=org_id)
    offer = await repo.get_by_id(offer_id)
    if offer is None:
        raise ValueError("yield offer not found")
    if offer.status != YieldOfferStatus.PENDING:
        raise ValueError(f"yield offer is {offer.status.value}, not pending")
    if offer.target_user_id == new_target_user_id:
        raise ValueError("offer is already targeted at this user")

    bud_repo = BUDRepository(db, org_id=org_id)
    incoming = await bud_repo.get_by_id(offer.incoming_bud_id)
    if incoming is None:
        raise ValueError("offer references a deleted incoming BUD")
    incoming_weight = BUD_PRIORITY_WEIGHTS[incoming.priority]

    new_yieldable = await bud_repo.lowest_priority_active_for_assignee(
        new_target_user_id, [s.value for s in TERMINAL_BUD_STATUSES]
    )
    if new_yieldable is None:
        raise ValueError("new target has no active BUD to yield")
    if BUD_PRIORITY_WEIGHTS[new_yieldable.priority] >= incoming_weight:
        raise ValueError(
            "new target's lowest-priority BUD is not strictly lower than the incoming BUD"
        )

    old_target_id = offer.target_user_id
    offer.target_user_id = new_target_user_id
    offer.yieldable_bud_id = new_yieldable.id
    await db.flush()

    # Old target's UI must drop the row; new target's UI must show it.
    publish(
        f"yield_offer:{old_target_id}",
        {
            "event": "resolved",
            "offer_id": str(offer.id),
            "org_id": str(org_id),
            "target_user_id": str(old_target_id),
            "resolution": "reassigned",
        },
    )
    publish(
        f"yield_offer:{new_target_user_id}",
        {
            "event": "created",
            "offer_id": str(offer.id),
            "org_id": str(org_id),
            "target_user_id": str(new_target_user_id),
            "incoming_bud_id": str(incoming.id),
            "incoming_bud_priority": incoming.priority.value,
            "yieldable_bud_id": str(new_yieldable.id),
            "yieldable_bud_priority": new_yieldable.priority.value,
        },
    )
    logger.info(
        "yield_offer_reassigned",
        offer_id=str(offer.id),
        from_user=str(old_target_id),
        to_user=str(new_target_user_id),
    )
    return offer


async def _find_best_yield_candidate(
    db: AsyncSession,
    org_id: uuid.UUID,
    incoming_bud: BUDDocument,
    saturated_candidates: list[User],
) -> tuple[User, BUDDocument] | None:
    """Return (user, their lowest-priority active BUD) with the biggest gap.

    A candidate qualifies only when their lowest-priority active BUD is
    strictly lower-priority than ``incoming_bud``. Ranking is by
    ``incoming_weight - yieldable_weight`` descending so we prefer
    candidates whose work is most-clearly displaceable.
    """
    bud_repo = BUDRepository(db, org_id=org_id)
    incoming_weight = BUD_PRIORITY_WEIGHTS[incoming_bud.priority]
    best: tuple[User, BUDDocument, int] | None = None

    for candidate in saturated_candidates:
        yieldable = await _lowest_priority_active_bud(bud_repo, candidate.id)
        if yieldable is None:
            continue
        gap = incoming_weight - BUD_PRIORITY_WEIGHTS[yieldable.priority]
        if gap <= 0:
            continue  # not strictly lower-priority
        if best is None or gap > best[2]:
            best = (candidate, yieldable, gap)

    if best is None:
        return None
    return best[0], best[1]


async def _lowest_priority_active_bud(
    bud_repo: BUDRepository, user_id: uuid.UUID
) -> BUDDocument | None:
    """Return the candidate's lowest-priority active BUD, or ``None``."""
    return await bud_repo.lowest_priority_active_for_assignee(
        user_id, [s.value for s in TERMINAL_BUD_STATUSES]
    )


def _guard_actor(
    offer: YieldOffer | None,
    acting_user_id: uuid.UUID,
    *,
    expected_status: YieldOfferStatus,
) -> None:
    """Reject access by anyone but the offer's target while the offer is open."""
    if offer is None:
        raise ValueError("yield offer not found")
    if offer.target_user_id != acting_user_id:
        raise ValueError("yield offer not addressed to this user")
    if offer.status != expected_status:
        raise ValueError(f"yield offer is {offer.status.value}, not {expected_status.value}")


__all__ = [
    "YIELD_OFFER_TTL",
    "accept_offer",
    "list_org_pending_with_expiry",
    "list_pending_with_expiry",
    "maybe_raise_yield_offer",
    "reassign_offer",
    "reject_offer",
]
