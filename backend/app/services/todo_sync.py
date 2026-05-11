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

"""Upsert BUDTodo records from a parsed tech spec.

Kept separate from ``todo_parser`` (pure) and ``agent_result_handlers``
(orchestration) so each layer has a single responsibility:

  tech_spec_md → todo_parser (pure)  → ParsedTodo[]
                     ↓
                todo_sync (DB)      → BUDTodo rows
                     ↑
           agent_result_handlers calls this
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud_todo import BUDTodo, BUDTodoStatus
from app.repositories.bud_todo import BUDTodoRepository
from app.services.todo_parser import ParsedTodo, parse_implementation_todos

logger = structlog.get_logger(__name__)


async def sync_todos_from_tech_spec(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    tech_spec_md: str | None,
    default_assignee_id: uuid.UUID | None = None,
) -> int:
    """Parse the tech spec and sync ``BUDTodo`` rows for a BUD.

    Sync rules:
      - New sequence → insert with ``default_assignee_id`` and status pending
      - Existing sequence → update title + context_md + is_checkpoint
        (preserve assignee + status — a developer may already be working)
      - Removed sequence with status pending → delete (safe, not started)
      - Removed sequence with other status → keep (audit trail)

    Returns the number of TODOs parsed (new + updated).
    Returns 0 when the spec has no parseable TODO section — the caller
    should treat this as "use existing single-assignee workflow".
    """
    parsed = parse_implementation_todos(tech_spec_md)
    if not parsed:
        return 0

    existing = await _load_existing_todos(db, org_id, bud_id)
    parsed_seqs = {p.sequence for p in parsed}

    for todo in parsed:
        current = existing.get(todo.sequence)
        if current is None:
            db.add(_build_new_todo(org_id, bud_id, todo, default_assignee_id))
        else:
            _apply_updates(current, todo)

    # Remove parsed-out TODOs only if never claimed.
    for seq, todo in existing.items():
        if seq in parsed_seqs:
            continue
        if todo.status == BUDTodoStatus.PENDING and todo.assignee_id is None:
            await db.delete(todo)

    await db.flush()
    logger.info(
        "bud_todos_synced",
        bud_id=str(bud_id),
        count=len(parsed),
    )
    return len(parsed)


async def _load_existing_todos(
    db: AsyncSession, org_id: uuid.UUID, bud_id: uuid.UUID
) -> dict[int, BUDTodo]:
    todos = await BUDTodoRepository(db, org_id=org_id).list_for_bud(bud_id)
    return {todo.sequence: todo for todo in todos}


def _build_new_todo(
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    parsed: ParsedTodo,
    default_assignee_id: uuid.UUID | None,
) -> BUDTodo:
    return BUDTodo(
        org_id=org_id,
        bud_id=bud_id,
        sequence=parsed.sequence,
        title=parsed.title,
        phase=parsed.phase,
        status=BUDTodoStatus.PENDING,
        is_checkpoint=parsed.is_checkpoint,
        # Checkpoints are review gates — leave unassigned regardless of default.
        assignee_id=None if parsed.is_checkpoint else default_assignee_id,
        context_md=parsed.context_md,
    )


def _apply_updates(current: BUDTodo, parsed: ParsedTodo) -> None:
    """Update content fields only — preserve assignee and status."""
    current.title = parsed.title
    current.phase = parsed.phase
    current.is_checkpoint = parsed.is_checkpoint
    current.context_md = parsed.context_md
