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
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.services.bud_estimation import estimate_bud_dates
from app.services.event_bus import publish
from app.services.todo_sync import sync_todos_from_tech_spec

logger = structlog.get_logger(__name__)


async def on_bud_development_started(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    actor_id: uuid.UUID | None = None,
    actor_name: str | None = None,
) -> None:
    """Run dev-transition side effects: todo regen, WS publish, estimation.

    Called from both transition paths (approval workflow + manual PATCH
    override) so behavior is symmetric. Each side-effect is independent
    and non-fatal — by the time we're here ``bud.status`` is already
    ``DEVELOPMENT`` and the caller has follow-up work (auto-assign,
    notifications) that must not be blocked by a parser or estimator
    glitch. Failures are logged and swallowed; the transaction is left
    intact for the caller to commit.
    """
    todo_count = await _sync_todos(db, org_id, bud)
    if todo_count > 0:
        _publish_regenerated(bud.id, todo_count)
    await _reestimate(db, org_id, bud, actor_id, actor_name)


async def _sync_todos(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> int:
    try:
        return await sync_todos_from_tech_spec(
            db, org_id, bud.id, bud.tech_spec_md, default_assignee_id=None
        )
    except Exception as exc:
        logger.warning(
            "todo_sync_failed_at_dev_transition",
            bud_id=str(bud.id),
            error=str(exc),
        )
        return 0


def _publish_regenerated(bud_id: uuid.UUID, todo_count: int) -> None:
    # Publish before commit, mirroring ``cascade_assignee_to_todos``: the
    # worst case on rollback is a redundant refetch from the frontend
    # that re-reads unchanged DB state — no consistency risk.
    publish(
        f"todo:{bud_id}",
        {
            "event": "todos_regenerated",
            "bud_id": str(bud_id),
            "todo_count": todo_count,
        },
    )


async def _reestimate(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    actor_id: uuid.UUID | None,
    actor_name: str | None,
) -> None:
    try:
        await estimate_bud_dates(
            db,
            org_id,
            bud,
            trigger="bud_development_started",
            actor_id=actor_id,
            actor_name=actor_name,
        )
    except Exception as exc:
        logger.warning(
            "estimation_failed_at_dev_transition",
            bud_id=str(bud.id),
            error=str(exc),
        )
