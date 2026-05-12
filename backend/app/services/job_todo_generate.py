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

"""Job handler for the ``todo_generate`` job type.

Runs the todo-generator agent in a job-queue worker (own DB session,
own asyncio task) so the HTTP request that triggers it returns fast.
Progress events are published on the ``todo:{bud_id}`` topic — the
Development tab subscribes there for live updates. Job-level state
(QUEUED → RUNNING → COMPLETED / FAILED) is mirrored on ``job:{job_id}``
by ``job_queue.update_job`` for any consumer that wants it.
"""

import uuid as uuid_mod
from typing import Any

import structlog

from app.database import AsyncSessionLocal
from app.repositories.bud import BUDRepository
from app.schemas.jobs import JobState, TodoGenerateJobPayload
from app.services.bud_estimation import estimate_bud_dates
from app.services.event_bus import publish
from app.services.job_queue import update_job
from app.services.todo_assignment import assign_all_todos_to_lead
from app.services.todo_sync import sync_todos_for_bud

logger = structlog.get_logger(__name__)


async def handle_todo_generate_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Generate (or regenerate) the TODO board for one BUD via the agent."""
    payload = TodoGenerateJobPayload(**raw_payload)
    bud_id = uuid_mod.UUID(payload.bud_id)
    org_id = uuid_mod.UUID(payload.org_id)
    topic = f"todo:{bud_id}"

    update_job(
        job_id,
        state=JobState.RUNNING,
        status_message="Generating TODOs from tech spec…",
        progress_pct=10,
    )

    async with AsyncSessionLocal() as db:
        bud = await BUDRepository(db, org_id=org_id).get_by_id(bud_id)
        if bud is None:
            _fail(job_id, topic, f"BUD {bud_id} not found")
            return

        try:
            count = await sync_todos_for_bud(db, org_id, bud, mode=payload.mode)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.exception("todo_generate_job_failed", bud_id=str(bud_id))
            _fail(job_id, topic, str(exc))
            return

        # Assign TODOs to the BUD's phase lead after the sync has
        # committed. The lead is set by ``auto_assign_for_phase`` in the
        # PATCH handler *after* the job is enqueued; running this after
        # the ~30s sync guarantees the PATCH transaction has committed
        # and the assignee_id is visible. Refresh to read past the
        # session cache. No-op on regenerate (developers already own
        # their TODOs via claim/takeover).
        if payload.mode == "initial":
            await db.refresh(bud, ["assignee_id"])
            if bud.assignee_id is not None:
                await assign_all_todos_to_lead(db, org_id, bud_id, bud.assignee_id)
                await db.commit()

        publish(
            topic,
            {
                "event": "todos_regenerated",
                "bud_id": str(bud_id),
                "todo_count": count,
            },
        )
        update_job(
            job_id,
            state=JobState.RUNNING,
            status_message="Re-estimating phase dates…",
            progress_pct=70,
        )
        # Re-estimate in the same worker — also a Claude call (~10-30s).
        # Failure is non-fatal; the TODOs are already committed.
        await _reestimate(db, org_id, bud, payload)

    update_job(
        job_id,
        state=JobState.COMPLETED,
        status_message=f"Generated {count} TODOs",
        progress_pct=100,
        result={"todo_count": count, "mode": payload.mode},
    )


async def _reestimate(
    db: Any,
    org_id: uuid_mod.UUID,
    bud: Any,
    payload: TodoGenerateJobPayload,
) -> None:
    """Run the PERT estimator. Non-fatal: errors are logged + swallowed."""
    actor_id = uuid_mod.UUID(payload.actor_id) if payload.actor_id else None
    try:
        await estimate_bud_dates(
            db,
            org_id,
            bud,
            trigger="bud_development_started",
            actor_id=actor_id,
            actor_name=payload.actor_name,
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning(
            "estimation_failed_in_todo_job",
            bud_id=str(bud.id),
            error=str(exc),
        )


def _fail(job_id: str, topic: str, error: str) -> None:
    publish(topic, {"event": "generating_failed", "error": error})
    update_job(job_id, state=JobState.FAILED, error=error)
