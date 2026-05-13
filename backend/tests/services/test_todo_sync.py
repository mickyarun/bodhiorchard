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

"""Tests for the reconciliation rules in ``todo_sync._reconcile``.

The agent-call path is exercised by ``test_todo_generator.py``; here we
cover only the diff logic that decides insert / update / preserve / delete
per sequence — the part most likely to nuke in-flight developer work.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.bud_todo import BUDTodo, BUDTodoStatus
from app.schemas.bud_todo_generator import TodoGeneratorItem
from app.services import todo_sync
from app.services.todo_generator import TodoGenerationError
from app.services.todo_sync import _is_preserved, _reconcile, sync_todos_for_bud


def _item(sequence: int, **overrides: object) -> TodoGeneratorItem:
    base: dict[str, object] = {
        "sequence": sequence,
        "title": f"Task {sequence}",
        "description": None,
        "repo_name": None,
        "code_locations": [],
        "context_md": None,
        "is_checkpoint": False,
        "phase": "development",
    }
    base.update(overrides)
    return TodoGeneratorItem.model_validate(base)


def _existing(
    sequence: int,
    *,
    status: BUDTodoStatus = BUDTodoStatus.PENDING,
    assignee_id: uuid.UUID | None = None,
    summary: str | None = None,
    title: str = "old title",
) -> BUDTodo:
    return BUDTodo(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        bud_id=uuid.uuid4(),
        sequence=sequence,
        title=title,
        phase="development",
        status=status,
        is_checkpoint=False,
        assignee_id=assignee_id,
        summary=summary,
    )


class _RecordingSession:
    """Minimal stand-in for AsyncSession used by `_reconcile`."""

    def __init__(self) -> None:
        self.added: list[BUDTodo] = []
        self.deleted: list[BUDTodo] = []

    def add(self, obj: BUDTodo) -> None:
        self.added.append(obj)

    async def delete(self, obj: BUDTodo) -> None:
        self.deleted.append(obj)


# ── preservation predicate ─────────────────────────────────────────


def test_pending_unassigned_no_summary_is_not_preserved() -> None:
    assert _is_preserved(_existing(1)) is False


def test_completed_is_preserved() -> None:
    assert _is_preserved(_existing(1, status=BUDTodoStatus.COMPLETED)) is True


def test_assigned_is_preserved() -> None:
    assert _is_preserved(_existing(1, assignee_id=uuid.uuid4())) is True


def test_summary_set_is_preserved() -> None:
    assert _is_preserved(_existing(1, summary="done")) is True


# ── reconciliation matrix ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_new_sequence_is_inserted() -> None:
    db = _RecordingSession()
    ins, upd, pres, dlt = await _reconcile(
        db,  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        bud_id=uuid.uuid4(),
        agent_items=[_item(1, title="fresh")],
        existing={},
    )
    assert (ins, upd, pres, dlt) == (1, 0, 0, 0)
    assert len(db.added) == 1
    assert db.added[0].title == "fresh"


@pytest.mark.asyncio
async def test_existing_fresh_sequence_is_updated_in_place() -> None:
    existing = {1: _existing(1, title="stale")}
    db = _RecordingSession()
    ins, upd, _pres, _dlt = await _reconcile(
        db,  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        bud_id=uuid.uuid4(),
        agent_items=[_item(1, title="refreshed")],
        existing=existing,
    )
    assert (ins, upd) == (0, 1)
    assert existing[1].title == "refreshed"
    assert db.added == []


@pytest.mark.asyncio
async def test_update_writes_empty_list_not_null_for_code_locations() -> None:
    """``code_locations`` is NOT NULL in DB — never coerce empty list to None."""
    existing = {1: _existing(1)}
    db = _RecordingSession()
    await _reconcile(
        db,  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        bud_id=uuid.uuid4(),
        agent_items=[_item(1, code_locations=[])],
        existing=existing,
    )
    assert existing[1].code_locations == []


@pytest.mark.asyncio
async def test_preserved_existing_is_left_alone_even_when_agent_emits_same_seq() -> None:
    existing = {1: _existing(1, status=BUDTodoStatus.IN_PROGRESS, title="claimed")}
    db = _RecordingSession()
    _ins, upd, pres, _dlt = await _reconcile(
        db,  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        bud_id=uuid.uuid4(),
        agent_items=[_item(1, title="agent-rewrite")],
        existing=existing,
    )
    assert (upd, pres) == (0, 1)
    # Title must remain the in-progress version — developer is mid-task.
    assert existing[1].title == "claimed"


@pytest.mark.asyncio
async def test_pending_unassigned_dropped_when_agent_no_longer_emits_it() -> None:
    stale = _existing(2, title="agent dropped me")
    db = _RecordingSession()
    _ins, _upd, _pres, dlt = await _reconcile(
        db,  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        bud_id=uuid.uuid4(),
        agent_items=[],
        existing={2: stale},
    )
    assert dlt == 1
    assert db.deleted == [stale]


@pytest.mark.asyncio
async def test_preserved_existing_kept_when_agent_drops_the_sequence() -> None:
    claimed = _existing(2, assignee_id=uuid.uuid4(), title="being worked")
    db = _RecordingSession()
    _ins, _upd, pres, dlt = await _reconcile(
        db,  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        bud_id=uuid.uuid4(),
        agent_items=[],
        existing={2: claimed},
    )
    assert (pres, dlt) == (1, 0)
    assert db.deleted == []


@pytest.mark.asyncio
async def test_agent_failure_propagates_to_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: agent timeout / crash must NOT be silently swallowed.

    Previously ``sync_todos_for_bud`` caught ``TodoGenerationError`` and
    returned 0, causing the worker to emit ``todos_regenerated`` +
    ``skill_completed`` for an agent that never ran — the user saw
    "Generated 0 TODOs" instead of the real timeout error. The fix
    propagates so the worker's _fail() path runs.
    """
    bud = SimpleNamespace(
        id=uuid.uuid4(),
        bud_number=1,
        title="Test BUD",
        impacted_repos=[],
    )
    monkeypatch.setattr(
        todo_sync,
        "generate_todos_for_bud",
        AsyncMock(side_effect=TodoGenerationError("agent timed out after 180s")),
    )

    with pytest.raises(TodoGenerationError, match="timed out"):
        await sync_todos_for_bud(MagicMock(), uuid.uuid4(), bud, mode="regenerate")  # type: ignore[arg-type]
