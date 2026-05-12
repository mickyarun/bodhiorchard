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
manual editing). Todos are derived state that should crystallize once,
when the approved plan is locked in by the dev-phase transition. Mirrors
the ``on_bud_closed`` pattern in ``bud_closure.py``.

All Claude work for this transition (TODO generation **and** PERT
re-estimation) runs inside the ``JOB_TODO_GENERATE`` worker so the HTTP
PATCH that triggers the transition returns in tens of milliseconds.
That keeps the frontend's axios timeout (30s) comfortably clear and
ensures the Development tab is mounted — and subscribed to the
``todo:{bud_id}`` topic — before the agent starts publishing progress
events.
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.schemas.jobs import TodoGenerateJobPayload
from app.services.event_bus import publish
from app.services.job_queue import JOB_TODO_GENERATE, create_job

logger = structlog.get_logger(__name__)


async def on_bud_development_started(
    db: AsyncSession,  # noqa: ARG001 — kept for caller signature compatibility
    org_id: uuid.UUID,
    bud: BUDDocument,
    actor_id: uuid.UUID | None = None,
    actor_name: str | None = None,
) -> None:
    """Enqueue the dev-transition work. Returns in ~tens of ms.

    Both the TODO-generator agent and the PERT re-estimator are Claude
    calls (each ~10-30s); both run in the ``JOB_TODO_GENERATE`` worker
    so this PATCH path stays fast. Frontend reacts to events on the
    ``todo:{bud_id}`` topic.
    """
    try:
        payload = TodoGenerateJobPayload(
            org_id=str(org_id),
            bud_id=str(bud.id),
            mode="initial",
            actor_id=str(actor_id) if actor_id else None,
            actor_name=actor_name,
        )
        create_job(
            JOB_TODO_GENERATE,
            payload=payload.model_dump(),
            user_id=str(actor_id) if actor_id else None,
        )
    except Exception as exc:
        # Enqueue failure must not block the PATCH; surface via WS so
        # the UI shows the error instead of a stuck spinner.
        logger.warning(
            "todo_generate_enqueue_failed",
            bud_id=str(bud.id),
            error=str(exc),
        )
        publish(
            f"todo:{bud.id}",
            {"event": "generating_failed", "error": str(exc)},
        )
