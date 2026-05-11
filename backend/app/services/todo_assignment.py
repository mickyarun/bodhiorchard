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

"""Default TODO assignment on DEVELOPMENT entry.

On DEVELOPMENT entry the BUD's phase lead (chosen by smart assignment)
owns every TODO. Other developers can pick up individual items via the
Claim UI or the MCP ``takeover_todo`` tool — that is the only way a
TODO transfers hands.
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud_todo import BUDTodo
from app.repositories.bud_todo import BUDTodoRepository
from app.services.event_bus import publish

logger = structlog.get_logger(__name__)


async def assign_all_todos_to_lead(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    lead_user_id: uuid.UUID,
) -> int:
    """Assign every unassigned non-checkpoint TODO to the phase lead.

    Preserves the existing single-owner-per-BUD mental model. Other
    developers can self-assign individual TODOs afterwards via the UI
    or MCP ``takeover_todo``.

    Returns the number of TODOs newly assigned.
    """
    unassigned = await _list_unassigned_non_checkpoint_todos(db, org_id, bud_id)
    if not unassigned:
        return 0

    for todo in unassigned:
        todo.assignee_id = lead_user_id

    await db.flush()
    logger.info(
        "todo_assigned_to_lead",
        bud_id=str(bud_id),
        lead_user_id=str(lead_user_id),
        assigned=len(unassigned),
    )
    return len(unassigned)


async def _list_unassigned_non_checkpoint_todos(
    db: AsyncSession, org_id: uuid.UUID, bud_id: uuid.UUID
) -> list[BUDTodo]:
    return await BUDTodoRepository(db, org_id=org_id).list_unassigned_non_checkpoint_for_bud(
        bud_id
    )


async def cascade_assignee_to_todos(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    new_assignee_id: uuid.UUID,
) -> int:
    """Mirror a manual top-level BUD reassignment onto its TODOs.

    Only touches ``assignee_id`` — never status. Aborts (returns ``-1``)
    if any non-checkpoint TODO is in_progress, completed, or has been
    taken over (``taken_at IS NOT NULL``); we never overwrite a
    developer's claim with a top-level reassignment. Returns the count
    of TODOs whose assignee changed when the cascade ran.

    Caller is responsible for restricting this to DEVELOPMENT phase —
    other phases don't have per-TODO ownership semantics yet.
    """
    repo = BUDTodoRepository(db, org_id=org_id)
    if await repo.has_active_or_taken_todos(bud_id):
        logger.info(
            "todo_cascade_skipped_work_in_progress",
            bud_id=str(bud_id),
            new_assignee_id=str(new_assignee_id),
        )
        return -1

    todos = await repo.list_non_checkpoint_for_bud(bud_id)
    changed = 0
    for todo in todos:
        if todo.assignee_id != new_assignee_id:
            todo.assignee_id = new_assignee_id
            changed += 1

    if changed:
        await db.flush()
        # Publish before commit, mirroring the ``todo_claimed`` path in
        # ``api/v1/bud_todos.py``. If the outer transaction later rolls
        # back, the worst case is a redundant refetch from the frontend
        # that re-reads the unchanged DB state — no consistency risk
        # because every subscriber re-queries the source of truth.
        publish(
            f"todo:{bud_id}",
            {
                "event": "assignee_cascaded",
                "bud_id": str(bud_id),
                "new_assignee_id": str(new_assignee_id),
                "changed_count": changed,
            },
        )
    logger.info(
        "todo_cascade_assigned",
        bud_id=str(bud_id),
        new_assignee_id=str(new_assignee_id),
        changed=changed,
    )
    return changed
