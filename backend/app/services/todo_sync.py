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

"""Sync ``BUDTodo`` rows from the tech spec's Implementation TODO section.

Runs the deterministic :mod:`todo_parser` against ``bud.tech_spec_md``
and reconciles the result against existing rows by sequence. In-flight
developer work (anything claimed, completed, or annotated with a
summary) is preserved verbatim.

The reconciler is the only writer of ``description`` / ``repo_name`` /
``code_locations`` / ``context_md`` / ``title`` / ``is_checkpoint`` —
those are derived from the parsed spec. ``status`` / ``assignee_id`` /
``summary`` / ``taken_at`` are user-owned and never touched here.
"""

import uuid
from typing import Literal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.bud_todo import BUDTodo, BUDTodoStatus
from app.repositories.bud_todo import BUDTodoRepository
from app.services.todo_parser import ParsedTodo, parse_implementation_todos

logger = structlog.get_logger(__name__)

SyncMode = Literal["initial", "regenerate"]


async def sync_todos_for_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    *,
    mode: SyncMode = "initial",
) -> int:
    """Re-derive BUDTodo rows for a BUD from its tech spec.

    ``mode`` distinguishes dev-phase transition from user-triggered
    regenerate; both follow identical reconciliation rules and the label
    is forwarded to the log. Returns the count of items the parser
    produced (zero when the spec has no Implementation TODO section).
    Flushes but does not commit — the caller owns the transaction.
    """
    known_repo_names = _known_repo_names(bud)
    parsed_items = parse_implementation_todos(
        bud.tech_spec_md,
        known_repo_names=known_repo_names,
    )
    if not parsed_items:
        logger.info(
            "bud_todos_no_section",
            bud_id=str(bud.id),
            mode=mode,
        )
        return 0

    existing = await _load_existing_by_sequence(db, org_id, bud.id)
    inserted, updated, preserved, deleted = await _reconcile(
        db,
        org_id=org_id,
        bud_id=bud.id,
        parsed_items=parsed_items,
        existing=existing,
    )

    await db.flush()
    logger.info(
        "bud_todos_synced",
        bud_id=str(bud.id),
        mode=mode,
        parsed_count=len(parsed_items),
        inserted=inserted,
        updated=updated,
        preserved=preserved,
        deleted=deleted,
    )
    return len(parsed_items)


def _known_repo_names(bud: BUDDocument) -> list[str]:
    """Project ``bud.impacted_repos`` into a flat list of repo names.

    The parser uses this list to validate ``— repo: <name>`` suffixes —
    a name not in the list resolves to ``None`` (cross-cutting) rather
    than silently binding the TODO to a typo'd repo.
    """
    names: list[str] = []
    for entry in bud.impacted_repos or []:
        repo_name = entry.get("repo_name") if isinstance(entry, dict) else None
        if repo_name:
            names.append(str(repo_name))
    return names


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
    parsed_items: list[ParsedTodo],
    existing: dict[int, BUDTodo],
) -> tuple[int, int, int, int]:
    """Apply insert/update/delete rules and return ``(ins, upd, pres, del)``."""
    inserted = updated = preserved = deleted = 0
    parsed_seqs = {item.sequence for item in parsed_items}

    for item in parsed_items:
        current = existing.get(item.sequence)
        if current is None:
            db.add(_build_new_todo(org_id, bud_id, item))
            inserted += 1
        elif _is_preserved(current):
            preserved += 1
        else:
            _apply_parsed_fields(current, item)
            updated += 1

    for seq, todo in existing.items():
        if seq in parsed_seqs:
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
    item: ParsedTodo,
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


def _apply_parsed_fields(current: BUDTodo, item: ParsedTodo) -> None:
    """Refresh parser-derived fields; never touch user-owned columns."""
    current.title = item.title
    current.description = item.description
    current.phase = item.phase
    current.is_checkpoint = item.is_checkpoint
    current.context_md = item.context_md
    current.repo_name = item.repo_name
    current.code_locations = item.code_locations
