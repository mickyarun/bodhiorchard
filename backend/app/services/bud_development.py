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

"""Side effects when a BUD enters the DEVELOPMENT phase.

The tech spec churns freely during planning (chat edits, agent re-runs,
manual editing). TODOs are derived state that crystallizes once, when the
approved plan is locked in by the dev-phase transition. Mirrors the
``on_bud_closed`` pattern in ``bud_closure.py``.

TODO sync is now a deterministic parse over ``bud.tech_spec_md`` — it
runs in the request transaction and completes in milliseconds. PERT
estimation is still an LLM call (~10–30s); it fires as a background
asyncio task with its own DB session so the PATCH that triggered the
transition returns immediately.
"""

import asyncio
import uuid

import structlog
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as SyncSession

from app.database import AsyncSessionLocal
from app.models.bud import BUDDocument
from app.repositories.bud import BUDRepository
from app.services.agent_activity_logger import log_agent_activity
from app.services.bud_estimation import estimate_bud_dates
from app.services.event_bus import publish
from app.services.todo_assignment import assign_all_todos_to_lead
from app.services.todo_sync import sync_todos_for_bud

logger = structlog.get_logger(__name__)

# Hold strong refs to in-flight PERT background tasks so the GC doesn't
# eat them mid-await; tasks remove themselves on completion. Same pattern
# documented in CLAUDE.md and used by github_app_slug._BACKGROUND_RETROFIT_TASKS.
_BACKGROUND_ESTIMATION_TASKS: set[asyncio.Task[None]] = set()

_ESTIMATOR_SLUG = "pert_estimator"


async def on_bud_development_started(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    actor_id: uuid.UUID | None = None,
    actor_name: str | None = None,
) -> None:
    """Crystallize the dev-phase plan: sync TODOs, assign to lead, kick off PERT.

    Runs synchronously inside the caller's transaction for the cheap
    work (TODO sync + lead assignment). The PERT estimator — still an
    LLM call — fires as a background task with its own session.

    Caller ordering: this hook must run AFTER ``auto_assign_for_phase``
    so ``bud.assignee_id`` is set on the model when we assign TODOs to
    the lead.
    """
    try:
        count = await sync_todos_for_bud(db, org_id, bud, mode="initial")
    except Exception as exc:
        # Surface the failure to the user via the activity feed AND raise
        # so the caller's whole transition (status change, auto-assign,
        # timeline events) unwinds together — half-applied state was the
        # silent-data-loss footgun a previous version of this hook hid by
        # catching + rolling back here. The caller's commit must own the
        # all-or-nothing decision.
        logger.warning(
            "todo_sync_failed_on_dev_start",
            bud_id=str(bud.id),
            error=str(exc),
        )
        publish(
            f"todo:{bud.id}",
            {"event": "generating_failed", "error": str(exc)},
        )
        raise

    if bud.assignee_id is not None:
        await assign_all_todos_to_lead(db, org_id, bud.id, bud.assignee_id)

    publish(
        f"todo:{bud.id}",
        {
            "event": "todos_regenerated",
            "bud_id": str(bud.id),
            "todo_count": count,
        },
    )

    # PERT runs on a fresh DB session; spawning right now would race the
    # caller's commit (the new session could read pre-transition state).
    # Defer the spawn until after the caller's transaction commits.
    _schedule_estimation_after_commit(
        db,
        org_id=org_id,
        bud_id=bud.id,
        actor_id=actor_id,
        actor_name=actor_name,
    )


def _schedule_estimation_after_commit(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    actor_name: str | None,
) -> None:
    """Defer the PERT estimator task to fire after the caller's commit.

    Registers a ``after_commit`` listener on the underlying sync session
    so the new DB session the task opens reads post-transition state
    (new status, lead assignee, freshly-inserted TODOs). Without this
    deferral the task races the caller's commit and may estimate on
    stale data. Estimation is non-fatal — failures are logged and
    surfaced to the activity log, never raised.
    """

    def _on_commit(_session: SyncSession) -> None:
        task = asyncio.create_task(
            _run_estimation(
                org_id=org_id,
                bud_id=bud_id,
                actor_id=actor_id,
                actor_name=actor_name,
            ),
            name=f"bg_estimate_bud_{bud_id}",
        )
        _BACKGROUND_ESTIMATION_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_ESTIMATION_TASKS.discard)

    event.listen(db.sync_session, "after_commit", _on_commit, once=True)


async def _run_estimation(
    *,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    actor_name: str | None,
) -> None:
    """Background task: re-estimate phase dates with a fresh DB session.

    Loads its own copy of the BUD because the caller's session is closed
    by the time this runs (intentional — we returned the request).
    """
    async with AsyncSessionLocal() as db:
        bud = await BUDRepository(db, org_id=org_id).get_by_id(bud_id)
        if bud is None:
            logger.warning("estimation_skipped_bud_missing", bud_id=str(bud_id))
            return

        await _emit_invoked(org_id, bud, "Re-estimating phase dates…")
        try:
            await estimate_bud_dates(
                db,
                org_id,
                bud,
                trigger="bud_development_started",
                actor_id=actor_id,
                actor_name=actor_name,
            )
            await db.commit()
            await _emit_completed(org_id, bud, "Phase dates updated")
        except Exception as exc:
            await db.rollback()
            logger.warning(
                "estimation_failed_in_background",
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


async def _emit_invoked(org_id: uuid.UUID, bud: BUDDocument, message: str) -> None:
    """Publish a ``skill_invoked`` lifecycle event for the activity banner."""
    await log_agent_activity(
        None,
        org_id=org_id,
        event_type="skill_invoked",
        skill_slug=_ESTIMATOR_SLUG,
        message=message,
        bud_id=bud.id,
        bud_number=bud.bud_number,
        bud_title=bud.title,
    )


async def _emit_completed(org_id: uuid.UUID, bud: BUDDocument, message: str) -> None:
    """Publish a ``skill_completed`` lifecycle event for the activity banner."""
    await log_agent_activity(
        None,
        org_id=org_id,
        event_type="skill_completed",
        skill_slug=_ESTIMATOR_SLUG,
        message=message,
        bud_id=bud.id,
        bud_number=bud.bud_number,
        bud_title=bud.title,
    )
