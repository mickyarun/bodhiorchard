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

"""Bring a discarded BUD back into the active pipeline.

Discarding is a soft terminal state: the BUD keeps every section, its
timeline and its linked feature row (deactivated, never deleted). Restore
is the exact inverse — it returns the BUD to the phase it occupied at the
moment it was discarded and revives that feature.

Closed BUDs are deliberately NOT restorable here. ``closed`` means
shipped, and reopening one would put a BUD that has already run
``on_bud_closed`` (XP, SP, learning metrics, Learning Agent) back into a
state where closing it again would re-fire all of it. ``discarded`` runs
none of those hooks, which is what makes it safe to undo.

Restore is intentionally side-effect-light: no agent job is enqueued and
no auto-assignment runs. Coming back from the bin is a bookkeeping
correction, not a phase advance — the user drives the BUD forward from
the restored phase using the normal status menu, which fires those hooks
the same way it always does.
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.user import User
from app.repositories.bud_timeline import BUDTimelineRepository
from app.repositories.organization import OrganizationRepository
from app.services.bud_timeline import record_event
from app.services.feature_lifecycle import restore_feature_for_bud
from app.services.org_settings import get_phase_order

logger = structlog.get_logger()

# Where a BUD lands when its pre-discard phase can't be used — no
# recorded transition (discarded via a path that predates the timeline
# event, or by an importer), an unparseable value, or a phase the org has
# since turned off. The first phase is always available and always safe.
RESTORE_FALLBACK_STATUS = BUDStatus.BUD


async def resolve_restore_status(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> BUDStatus:
    """Pick the phase a discarded BUD should return to.

    Reads the newest ``status_change`` event into ``discarded`` and takes
    its ``from`` phase, so a BUD binned during testing comes back in
    testing rather than restarting the pipeline.

    The candidate is validated against the org's *enabled* phase order
    (``get_phase_order`` strips ``uat`` when the org has it disabled).
    Without that check a BUD discarded from UAT in an org that later
    turned UAT off would be restored into a column the board never
    renders — visible in the API, invisible in the UI. That filter also
    rejects ``closed``/``discarded`` for free, since neither is a
    pipeline phase, so a discard-after-close can't resurrect a shipped
    BUD into its terminal state.
    """
    timeline_repo = BUDTimelineRepository(db, org_id=org_id)
    previous = await timeline_repo.latest_status_change_from(bud.id, BUDStatus.DISCARDED.value)
    if previous is None:
        return RESTORE_FALLBACK_STATUS

    org = await OrganizationRepository(db).get_by_id(org_id)
    enabled_phases = set(get_phase_order(org.config if org else None))
    if previous not in enabled_phases:
        logger.info(
            "bud_restore_phase_unavailable",
            bud_id=str(bud.id),
            previous_phase=previous,
            fallback=RESTORE_FALLBACK_STATUS.value,
        )
        return RESTORE_FALLBACK_STATUS
    return BUDStatus(previous)


async def restore_discarded_bud(
    db: AsyncSession,
    bud: BUDDocument,
    current_user: User,
) -> BUDStatus:
    """Move ``bud`` out of ``discarded`` and back into its previous phase.

    Records a normal ``status_change`` timeline event (tagged
    ``restored``) so the board, the activity feed and every consumer that
    already understands status changes pick the restore up without
    special-casing a new event type. Returns the phase landed on.

    Callers must have verified ``bud.status is BUDStatus.DISCARDED``.
    """
    target = await resolve_restore_status(db, current_user.org_id, bud)

    await restore_feature_for_bud(db, current_user.org_id, bud.bud_number)

    await record_event(
        db,
        current_user.org_id,
        bud.id,
        "status_change",
        actor_id=current_user.id,
        actor_name=current_user.name,
        detail={
            "from": BUDStatus.DISCARDED.value,
            "to": target.value,
            "restored": True,
        },
    )

    # Discard freezes the estimation columns rather than clearing them, so
    # a BUD binned three weeks into development returns carrying a deadline
    # three weeks in the past. That is not cosmetic: the standup risk
    # detector (``BUDRepository.list_lagging_in_statuses``) selects on
    # ``current_phase_deadline < now()``, and the board paints the card's
    # phase line red — a BUD would come back already "late" for time it
    # spent in the bin. Null both instead of recomputing here: the
    # estimator is an AI-PERT + Monte Carlo run, far too heavy (and too
    # failure-prone) to hold a restore open, and "not set" renders as
    # absent everywhere. The next estimation run re-derives them from the
    # phase the BUD actually resumes at.
    bud.current_phase_deadline = None
    bud.prod_p70_date = None

    bud.status = target
    await db.flush()
    await db.refresh(bud)

    logger.info(
        "bud_restored",
        bud_id=str(bud.id),
        bud_number=bud.bud_number,
        restored_to=target.value,
        actor_id=str(current_user.id),
    )
    return target
