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

"""Split the BUD-shipped Skill-Point pool across the people who did the work.

Replaces the old assignee-only award (which silently paid nobody when the
assignee's role wasn't a developer — the live BUD-029 failure). Recipients
are resolved from **what actually happened on the BUD**, never from who
closed it, so a BUD closed by anyone still credits the right people:

1. Assignees of **completed** todos, each weighted by the substance of
   their completed todos (the judge down-weights icon/copy-only work).
2. Fallback — assignees of **any** assigned todo (work claimed but no
   todo reached "completed"), weighted equally.
3. Last resort — commit / PR contributors via ``get_bud_contributors``.

The fixed pool (``SP_DEV_BUD_SHIPPED``) is divided by ``sp_split`` so a
multi-developer BUD still mints exactly one BUD's worth of SP, kept scarce.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.bud_todo import BUDTodo, BUDTodoStatus
from app.repositories.bud_todo import BUDTodoRepository
from app.services.contributor_resolver import get_bud_contributors

logger = structlog.get_logger(__name__)


def _completed_assignee_todos(todos: list[BUDTodo]) -> list[BUDTodo]:
    """Completed, non-checkpoint todos that have an assignee."""
    return [
        t
        for t in todos
        if t.status == BUDTodoStatus.COMPLETED.value
        and not t.is_checkpoint
        and t.assignee_id is not None
    ]


def _weights_from_completed(
    completed: list[BUDTodo],
    todo_weights: dict[str, float] | None,
) -> dict[uuid.UUID, float]:
    """Aggregate per-assignee weight from completed todos.

    Each completed todo contributes its substance weight (from the judge,
    default 1.0 when unjudged) to its assignee's total. An assignee whose
    every todo scored ~0 (all trivial) ends near 0 and is dropped by the
    splitter, so a pure icon-changer earns nothing.
    """
    weights: dict[uuid.UUID, float] = {}
    for todo in completed:
        assignee = todo.assignee_id
        if assignee is None:
            continue
        weight = 1.0 if todo_weights is None else todo_weights.get(str(todo.id), 1.0)
        weights[assignee] = weights.get(assignee, 0.0) + weight
    return weights


async def resolve_shipped_weights(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    todo_weights: dict[str, float] | None,
) -> dict[uuid.UUID, float]:
    """Resolve the per-recipient weight map via the recipient cascade."""
    todo_repo = BUDTodoRepository(db, org_id=org_id)
    todos = await todo_repo.list_for_bud(bud.id)

    completed = _completed_assignee_todos(todos)
    if completed:
        weights = _weights_from_completed(completed, todo_weights)
        if weights:
            return weights

    assigned = await todo_repo.assigned_distinct_assignees(bud.id)
    if assigned:
        return {uid: 1.0 for uid in assigned}

    contributors = await get_bud_contributors(db, org_id, bud.id)
    return {uid: 1.0 for uid in contributors}
