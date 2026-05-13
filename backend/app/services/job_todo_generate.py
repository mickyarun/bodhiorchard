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
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.bud import BUDDocument
from app.repositories.bud import BUDRepository
from app.schemas.jobs import JobState, TodoGenerateJobPayload
from app.services.agent_activity_logger import log_agent_activity
from app.services.bud_estimation import estimate_bud_dates
from app.services.event_bus import publish
from app.services.job_queue import update_job
from app.services.todo_assignment import assign_all_todos_to_lead
from app.services.todo_sync import sync_todos_for_bud

logger = structlog.get_logger(__name__)

# Synthetic skill slugs for the two Claude calls this worker drives.
# Frontend keys off these via the agent_activity:{org_id} topic to show
# stage-specific banner copy ("Generating implementation TODOs…",
# "Re-estimating phase dates…").
_TODO_SLUG = "todo_generator"
_ESTIMATOR_SLUG = "pert_estimator"


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
            await _fail(
                job_id,
                topic,
                org_id,
                bud_id,
                None,
                None,
                _TODO_SLUG,
                f"BUD {bud_id} not found",
            )
            return

        await _emit_invoked(org_id, bud, _TODO_SLUG, "Generating implementation TODOs…")

        try:
            count = await sync_todos_for_bud(db, org_id, bud, mode=payload.mode)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.exception("todo_generate_job_failed", bud_id=str(bud_id))
            await _fail(
                job_id,
                topic,
                org_id,
                bud_id,
                bud.bud_number,
                bud.title,
                _TODO_SLUG,
                str(exc),
            )
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
        await _emit_completed(
            org_id,
            bud,
            _TODO_SLUG,
            f"Generated {count} TODOs",
            metadata={"count": count, "mode": payload.mode},
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
    db: AsyncSession,
    org_id: uuid_mod.UUID,
    bud: BUDDocument,
    payload: TodoGenerateJobPayload,
) -> None:
    """Run the PERT estimator. Non-fatal: errors are logged + swallowed."""
    actor_id = uuid_mod.UUID(payload.actor_id) if payload.actor_id else None
    await _emit_invoked(org_id, bud, _ESTIMATOR_SLUG, "Re-estimating phase dates…")
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
        await _emit_completed(org_id, bud, _ESTIMATOR_SLUG, "Phase dates updated")
    except Exception as exc:
        await db.rollback()
        logger.warning(
            "estimation_failed_in_todo_job",
            bud_id=str(bud.id),
            error=str(exc),
        )
        await log_agent_activity(
            None,
            org_id=org_id,
            event_type="skill_failed",
            skill_slug=_ESTIMATOR_SLUG,
            message=f"Estimation failed: {exc}",
            bud_id=bud.id,
            bud_number=bud.bud_number,
            bud_title=bud.title,
            metadata_={"error": str(exc)},
        )


async def _emit_invoked(
    org_id: uuid_mod.UUID,
    bud: BUDDocument,
    skill_slug: str,
    message: str,
) -> None:
    """Publish a ``skill_invoked`` lifecycle event for the BUD banner.

    Always uses a fresh DB session so the audit row commits independently
    of the calling worker's transaction. Otherwise a later rollback in the
    worker (e.g. failed estimation) would silently discard already-published
    invoked/completed rows, leaving the WS event stream out of sync with
    the audit trail.
    """
    await log_agent_activity(
        None,
        org_id=org_id,
        event_type="skill_invoked",
        skill_slug=skill_slug,
        message=message,
        bud_id=bud.id,
        bud_number=bud.bud_number,
        bud_title=bud.title,
    )


async def _emit_completed(
    org_id: uuid_mod.UUID,
    bud: BUDDocument,
    skill_slug: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Publish a ``skill_completed`` lifecycle event for the BUD banner.

    Same fresh-session rationale as ``_emit_invoked``.
    """
    await log_agent_activity(
        None,
        org_id=org_id,
        event_type="skill_completed",
        skill_slug=skill_slug,
        message=message,
        bud_id=bud.id,
        bud_number=bud.bud_number,
        bud_title=bud.title,
        metadata_=metadata,
    )


async def _fail(
    job_id: str,
    topic: str,
    org_id: uuid_mod.UUID,
    bud_id: uuid_mod.UUID,
    bud_number: int | None,
    bud_title: str | None,
    skill_slug: str,
    error: str,
) -> None:
    """Mark the job failed; banner event first so the order matches the user-visible state."""
    # Publish the banner event first: BUDWorkflowActions decrements the
    # in-flight counter on `skill_failed`, which is the correct end-state
    # before BUDTodoBoard sees `generating_failed` and clears its hints.
    # Swallow logging exceptions — a DB hiccup writing the audit row must
    # never block the job-state update below; the user sees a stuck
    # RUNNING badge forever otherwise.
    try:
        await log_agent_activity(
            None,
            org_id=org_id,
            event_type="skill_failed",
            skill_slug=skill_slug,
            message=error,
            bud_id=bud_id,
            bud_number=bud_number,
            bud_title=bud_title,
            metadata_={"error": error},
        )
    except Exception:
        logger.warning("job_fail_skill_failed_log_failed", job_id=job_id, exc_info=True)
    publish(topic, {"event": "generating_failed", "error": error})
    update_job(job_id, state=JobState.FAILED, error=error)
