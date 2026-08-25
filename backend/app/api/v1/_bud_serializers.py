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

"""BUD ORM → Pydantic serialiser.

Pulled out of ``api/v1/bud.py`` so every route that returns a single BUD
can share it. ``bud.py`` mounts the sub-routers (``bud_workflows``,
``bud_qa``, …), so those modules cannot import back from it — a helper
living in the route file is only reachable by that file. Anything
returning ``BUDRead`` from a sub-router either duplicates the enrichment
or silently ships a thinner payload; this module is the shared home that
removes the choice.

The enrichment is not cosmetic: ``BUDDesignRead.repo_name`` has no ORM
column or relationship behind it, so plain ``from_attributes``
validation leaves it ``None`` and the design banners fall back to
"default".
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.repositories.agent_activity import AgentActivityLogRepository
from app.repositories.bud import BUDDesignRepository
from app.repositories.bud_agent_task import BUDAgentTaskRepository
from app.repositories.feature_learning import FeatureLearningRepository
from app.schemas.bud import BUDAgentTaskRead, BUDRead
from app.schemas.bud_design import BUDDesignRead
from app.services.agent_activity_logger import PHASE_WORKER_SLUGS
from app.services.bud_agent_trigger import should_auto_generate_phase
from app.services.yield_offer_lock import is_awaiting_human_decision


async def build_bud_response(
    bud: BUDDocument,
    org_id: uuid.UUID,
    db: AsyncSession,
) -> BUDRead:
    """Build BUDRead with active (or last-failed) agent task attached."""
    task_repo = BUDAgentTaskRepository(db, org_id=org_id)
    active_task = await task_repo.get_active_for_bud(bud.id)
    if not active_task:
        # Only show last-failed if no completed task exists after it (i.e. retry succeeded)
        failed = await task_repo.get_latest_failed(bud.id)
        if failed:
            completed = await task_repo.get_latest_completed(bud.id)
            if not completed or completed.created_at < failed.created_at:
                active_task = failed

    # `updated_at` has an ``onupdate=func.now()`` server default that
    # SQLAlchemy doesn't include in INSERT…RETURNING, so on a freshly
    # inserted BUD the attribute is "not loaded". Pydantic's sync
    # validator would then trigger a lazy SELECT — which can't spawn a
    # greenlet from sync context and raises MissingGreenlet. An explicit
    # refresh inside the async context eager-loads every column before
    # validation, and also picks up anything later phases (auto-assign,
    # agent-task creation) mutated on the same row.
    await db.refresh(bud)

    bud_data = BUDRead.model_validate(bud)
    if active_task:
        bud_data.active_agent_task = BUDAgentTaskRead.model_validate(active_task)

    # ``BUDDesignRead`` declares ``repo_name`` but the ORM model has no
    # column or relationship for it — ``from_attributes`` would leave
    # it None. Refetch designs via the JOIN-backed list so the per-repo
    # banners and chat-panel dropdown can render the actual repo name
    # instead of falling back to "default". Skip the extra query when
    # the BUD has no design rows (every non-design phase, plus design
    # phase before the user clicks "Add").
    if bud.designs:
        design_repo = BUDDesignRepository(db, org_id=org_id)
        design_rows = await design_repo.list_with_repo_names(bud.id)
        bud_data.designs = [BUDDesignRead.model_validate(row) for row in design_rows]

    # Re-attach the phase-progress banner for synthetic workers (assignment
    # / todo-gen / estimation) that don't have BUDAgentTask rows. Without
    # this the banner only catches events that fire AFTER mount, so the
    # whole chain is invisible if the user navigates away and back.
    # Uses the single source of truth ``PHASE_WORKER_SLUGS`` from
    # agent_activity_logger so adding a new worker touches exactly one
    # list.
    activity_repo = AgentActivityLogRepository(db, org_id=org_id)
    active_phase = await activity_repo.get_active_phase_worker(bud.id, PHASE_WORKER_SLUGS)
    if active_phase is not None:
        phase_payload = {
            "skill_slug": active_phase.skill_slug or "",
            "message": active_phase.message or "",
        }
        # A parked yield offer wears the same ``skill_invoked`` shape as a
        # running worker, but no agent is executing — the chain is waiting
        # on a person to accept or decline. Routing it to its own field
        # keeps the banner while leaving the status menu usable; treating
        # it as in-flight froze the BUD for the offer's whole 24h life.
        if is_awaiting_human_decision(active_phase):
            bud_data.awaiting_human_decision = phase_payload
        else:
            bud_data.active_phase_worker = phase_payload

    # Sticky failure banner: most recent skill_failed newer than the
    # user's dismissal timestamp. Covers the restart-recovery and
    # missed-WS-event cases without any client-side reconnect logic —
    # if the failure happened, the next BUD load surfaces it; the user
    # dismisses, the column updates, the banner is gone for good.
    latest_failure = await activity_repo.get_latest_skill_failed(
        bud.id,
        skill_slugs=PHASE_WORKER_SLUGS,
        since=bud.phase_failure_acknowledged_at,
    )
    if latest_failure is not None:
        bud_data.last_phase_failure = {
            "skill_slug": latest_failure.skill_slug or "",
            "message": latest_failure.message or "",
            "failed_at": latest_failure.created_at.isoformat()
            if latest_failure.created_at
            else None,
            "metadata": latest_failure.metadata_ or {},
        }

    # ``has_learning`` is a cheap tab-visibility flag. The tab shows when:
    #  - a row carries *either* the metrics envelope or the retrospective
    #    (gating on the recap alone hid restored metrics + the regenerate
    #    control when the Learning Agent failed but metrics succeeded), OR
    #  - the BUD is closed and opted into close-time AI but has no recap
    #    yet. That last case is the recovery path for a transient
    #    close-time failure that left *no* row at all (the prod incident on
    #    BUD-029/036): without it the tab stays hidden and the failure
    #    hides its own remedy — the user can never trigger a regenerate.
    # The full payload is fetched lazily via GET /buds/{id}/learning so the
    # BUD list stays small.
    learning_row = await FeatureLearningRepository(db, org_id=org_id).get_for_bud(bud.id)
    row_has_content = bool(
        learning_row and (learning_row.retrospective_md or learning_row.metrics)
    )
    awaiting_recap = bud.status == BUDStatus.CLOSED and should_auto_generate_phase(
        bud.auto_generate_phases, "closed"
    )
    bud_data.has_learning = row_has_content or awaiting_recap

    return bud_data
