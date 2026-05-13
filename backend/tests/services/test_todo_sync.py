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

"""Reconciliation rules in ``todo_sync._reconcile``.

The parser-call path is exercised by ``test_todo_parser.py``; here we
cover only the diff logic that decides insert / update / preserve /
delete per sequence — the part most likely to nuke in-flight developer
work.
"""

import uuid

import pytest

from app.models.bud_todo import BUDTodo, BUDTodoStatus
from app.services.todo_parser import ParsedTodo
from app.services.todo_sync import _is_preserved, _reconcile


def _parsed(sequence: int, **overrides: object) -> ParsedTodo:
    base: dict[str, object] = {
        "sequence": sequence,
        "title": f"Task {sequence}",
        "is_checkpoint": False,
        "phase": "development",
        "context_md": None,
        "description": None,
        "repo_name": None,
        "code_locations": [],
    }
    base.update(overrides)
    return ParsedTodo(**base)  # type: ignore[arg-type]


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
    """Minimal stand-in for AsyncSession used by ``_reconcile``."""

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
        parsed_items=[_parsed(1, title="fresh")],
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
        parsed_items=[_parsed(1, title="refreshed")],
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
        parsed_items=[_parsed(1, code_locations=[])],
        existing=existing,
    )
    assert existing[1].code_locations == []


@pytest.mark.asyncio
async def test_preserved_existing_is_left_alone_even_when_parser_emits_same_seq() -> None:
    existing = {1: _existing(1, status=BUDTodoStatus.IN_PROGRESS, title="claimed")}
    db = _RecordingSession()
    _ins, upd, pres, _dlt = await _reconcile(
        db,  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        bud_id=uuid.uuid4(),
        parsed_items=[_parsed(1, title="parser-rewrite")],
        existing=existing,
    )
    assert (upd, pres) == (0, 1)
    # Title must remain the in-progress version — developer is mid-task.
    assert existing[1].title == "claimed"


@pytest.mark.asyncio
async def test_pending_unassigned_dropped_when_parser_no_longer_emits_it() -> None:
    stale = _existing(2, title="parser dropped me")
    db = _RecordingSession()
    _ins, _upd, _pres, dlt = await _reconcile(
        db,  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        bud_id=uuid.uuid4(),
        parsed_items=[],
        existing={2: stale},
    )
    assert dlt == 1
    assert db.deleted == [stale]


@pytest.mark.asyncio
async def test_preserved_existing_kept_when_parser_drops_the_sequence() -> None:
    claimed = _existing(2, assignee_id=uuid.uuid4(), title="being worked")
    db = _RecordingSession()
    _ins, _upd, pres, dlt = await _reconcile(
        db,  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        bud_id=uuid.uuid4(),
        parsed_items=[],
        existing={2: claimed},
    )
    assert (pres, dlt) == (1, 0)
    assert db.deleted == []
