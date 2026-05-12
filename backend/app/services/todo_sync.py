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

"""Sync ``BUDTodo`` rows from the agent-generated breakdown of a tech spec.

Runs the ``todo-generator`` agent, reconciles its JSON output against
existing rows by sequence, and preserves in-flight developer work
(anything claimed, completed, or annotated with a summary stays put).

The reconciler is the only writer of ``description`` / ``repo_name`` /
``code_locations`` / ``context_md`` / ``title`` / ``is_checkpoint`` —
those are derived from the agent. ``status`` / ``assignee_id`` /
``summary`` / ``taken_at`` are user-owned and never touched here.
"""

import uuid
from typing import Literal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.bud_todo import BUDTodo, BUDTodoStatus
from app.repositories.bud_todo import BUDTodoRepository
from app.schemas.bud_todo_generator import TodoGeneratorItem
from app.services.todo_generator import TodoGenerationError, generate_todos_for_bud

logger = structlog.get_logger(__name__)

SyncMode = Literal["initial", "regenerate"]


async def sync_todos_for_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    *,
    mode: SyncMode = "initial",
) -> int:
    """Generate TODOs for a BUD via the agent and reconcile them in DB.

    ``mode`` distinguishes dev-phase transition from user-triggered
    regenerate; both follow identical reconciliation rules and the label
    is forwarded to the agent + logged. Returns the agent's item count,
    or 0 if the agent fails (BUD falls back to single-assignee flow).
    Flushes but does not commit — the caller owns the transaction.
    """
    impacted = _impacted_repo_pairs(bud)
    try:
        agent_items = await generate_todos_for_bud(bud, impacted, reason=mode)
    except TodoGenerationError as exc:
        logger.warning(
            "todo_sync_agent_failed",
            bud_id=str(bud.id),
            mode=mode,
            error=str(exc),
        )
        return 0
    if not agent_items:
        return 0

    existing = await _load_existing_by_sequence(db, org_id, bud.id)
    inserted, updated, preserved, deleted = await _reconcile(
        db,
        org_id=org_id,
        bud_id=bud.id,
        agent_items=agent_items,
        existing=existing,
    )

    await db.flush()
    logger.info(
        "bud_todos_synced",
        bud_id=str(bud.id),
        mode=mode,
        agent_count=len(agent_items),
        inserted=inserted,
        updated=updated,
        preserved=preserved,
        deleted=deleted,
    )
    return len(agent_items)


def _impacted_repo_pairs(bud: BUDDocument) -> list[tuple[uuid.UUID, str]]:
    """Project ``bud.impacted_repos`` into the (repo_id, repo_name) shape."""
    pairs: list[tuple[uuid.UUID, str]] = []
    for entry in bud.impacted_repos or []:
        repo_id = entry.get("repo_id") if isinstance(entry, dict) else None
        repo_name = entry.get("repo_name") if isinstance(entry, dict) else None
        if not repo_id or not repo_name:
            continue
        try:
            pairs.append((uuid.UUID(str(repo_id)), str(repo_name)))
        except (ValueError, TypeError):
            continue
    return pairs


async def _load_existing_by_sequence(
    db: AsyncSession, org_id: uuid.UUID, bud_id: uuid.UUID
) -> dict[int, BUDTodo]:
    todos = await BUDTodoRepository(db, org_id=org_id).list_for_bud(bud_id)
    return {todo.sequence: todo for todo in todos}


def _is_preserved(todo: BUDTodo) -> bool:
    """Anything a developer has touched stays exactly as-is on re-sync."""
    return (
        todo.status != BUDTodoStatus.PENDING
        or todo.assignee_id is not None
        or todo.summary is not None
    )


async def _reconcile(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    agent_items: list[TodoGeneratorItem],
    existing: dict[int, BUDTodo],
) -> tuple[int, int, int, int]:
    """Apply insert/update/delete rules and return ``(ins, upd, pres, del)``."""
    inserted = updated = preserved = deleted = 0
    agent_seqs = {item.sequence for item in agent_items}

    for item in agent_items:
        current = existing.get(item.sequence)
        if current is None:
            db.add(_build_new_todo(org_id, bud_id, item))
            inserted += 1
        elif _is_preserved(current):
            preserved += 1
        else:
            _apply_agent_fields(current, item)
            updated += 1

    for seq, todo in existing.items():
        if seq in agent_seqs:
            continue
        if _is_preserved(todo):
            preserved += 1
            continue
        await db.delete(todo)
        deleted += 1

    return inserted, updated, preserved, deleted


def _build_new_todo(
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    item: TodoGeneratorItem,
) -> BUDTodo:
    return BUDTodo(
        org_id=org_id,
        bud_id=bud_id,
        sequence=item.sequence,
        title=item.title,
        description=item.description,
        phase=item.phase,
        status=BUDTodoStatus.PENDING,
        is_checkpoint=item.is_checkpoint,
        assignee_id=None,
        context_md=item.context_md,
        repo_name=item.repo_name,
        code_locations=item.code_locations,
    )


def _apply_agent_fields(current: BUDTodo, item: TodoGeneratorItem) -> None:
    """Refresh agent-derived fields; never touch user-owned columns."""
    current.title = item.title
    current.description = item.description
    current.phase = item.phase
    current.is_checkpoint = item.is_checkpoint
    current.context_md = item.context_md
    current.repo_name = item.repo_name
    current.code_locations = item.code_locations
