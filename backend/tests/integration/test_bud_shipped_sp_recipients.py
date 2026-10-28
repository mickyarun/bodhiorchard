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

"""Who shares the BUD-shipped SP pool (``resolve_shipped_weights``).

Completed todos win, weighted by the judge's substance score; with none
completed, every assigned todo counts equally; with no todos assigned,
commit / PR contributors share it. Checkpoints never count, and the BUD
assignee or closer is never added on their own.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.bud import BUDDocument, BUDStatus
from app.models.bud_todo import BUDTodo, BUDTodoStatus
from app.services.bud_shipped_sp import resolve_shipped_weights
from tests.integration.bud_lifecycle_support import (
    Factory,
    add_bud,
    add_commit,
    add_member,
    new_org,
)
from tests.integration.bud_lifecycle_support import (
    app_database_blocked as app_database_blocked,
)

pytestmark = pytest.mark.integration


async def _todo(
    factory: Factory,
    org: uuid.UUID,
    bud_id: uuid.UUID,
    seq: int,
    assignee: uuid.UUID | None,
    status: BUDTodoStatus,
    *,
    checkpoint: bool = False,
) -> str:
    """Add a development todo and return its id as a string."""
    async with factory() as db:
        todo = BUDTodo(
            org_id=org,
            bud_id=bud_id,
            sequence=seq,
            title=f"todo {seq}",
            phase="development",
            status=status.value,
            assignee_id=assignee,
            is_checkpoint=checkpoint,
        )
        db.add(todo)
        await db.commit()
        return str(todo.id)


async def _weights(
    factory: Factory, org: uuid.UUID, bud_id: uuid.UUID, judged: dict[str, float] | None
) -> dict[uuid.UUID, float]:
    """Resolve the weight map in a fresh session."""
    async with factory() as db:
        bud = await db.get(BUDDocument, bud_id)
        assert bud is not None
        return await resolve_shipped_weights(db, org, bud, judged)


async def _bud(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Org, two developers and a closed BUD assigned to neither."""
    org = await new_org(factory)
    ada = await add_member(factory, org, "ada", role="developer")
    bob = await add_member(factory, org, "bob", role="developer")
    pm = await add_member(factory, org, "pm")
    bud_id = await add_bud(factory, org, status=BUDStatus.CLOSED, assignee_id=pm)
    return org, ada, bob, bud_id


async def test_completed_todos_are_weighted_by_substance(pg_session_factory: Factory) -> None:
    """Judge weights sum per assignee; an all-trivial assignee ends at zero."""
    org, ada, bob, bud_id = await _bud(pg_session_factory)
    a1 = await _todo(pg_session_factory, org, bud_id, 1, ada, BUDTodoStatus.COMPLETED)
    a2 = await _todo(pg_session_factory, org, bud_id, 2, ada, BUDTodoStatus.COMPLETED)
    b1 = await _todo(pg_session_factory, org, bud_id, 3, bob, BUDTodoStatus.COMPLETED)
    await _todo(pg_session_factory, org, bud_id, 4, bob, BUDTodoStatus.PENDING)

    weights = await _weights(pg_session_factory, org, bud_id, {a1: 1.0, a2: 0.5, b1: 0.0})

    assert weights == {ada: 1.5, bob: 0.0}


async def test_unjudged_completed_todos_weigh_one_each(pg_session_factory: Factory) -> None:
    """No verdict (single assignee): each completed todo counts 1.0."""
    org, ada, _bob, bud_id = await _bud(pg_session_factory)
    for seq in (1, 2):
        await _todo(pg_session_factory, org, bud_id, seq, ada, BUDTodoStatus.COMPLETED)

    assert await _weights(pg_session_factory, org, bud_id, None) == {ada: 2.0}


async def test_assigned_but_unfinished_todos_share_equally(pg_session_factory: Factory) -> None:
    """Nothing completed: every non-checkpoint assignee gets weight 1."""
    org, ada, bob, bud_id = await _bud(pg_session_factory)
    checkpoint_owner = await add_member(pg_session_factory, org, "cp", role="developer")
    await _todo(pg_session_factory, org, bud_id, 1, ada, BUDTodoStatus.IN_PROGRESS)
    await _todo(pg_session_factory, org, bud_id, 2, bob, BUDTodoStatus.BLOCKED)
    await _todo(
        pg_session_factory,
        org,
        bud_id,
        3,
        checkpoint_owner,
        BUDTodoStatus.COMPLETED,
        checkpoint=True,
    )

    assert await _weights(pg_session_factory, org, bud_id, None) == {ada: 1.0, bob: 1.0}


async def test_contributors_are_the_last_resort(pg_session_factory: Factory) -> None:
    """No assigned todos: committers share; the BUD assignee is not added."""
    org, ada, _bob, bud_id = await _bud(pg_session_factory)
    await _todo(pg_session_factory, org, bud_id, 1, None, BUDTodoStatus.COMPLETED)
    await add_commit(pg_session_factory, org, bud_id, ada)

    assert await _weights(pg_session_factory, org, bud_id, None) == {ada: 1.0}


async def test_no_work_at_all_means_no_recipients(pg_session_factory: Factory) -> None:
    """An empty BUD pays nobody, not even its assignee."""
    org, _ada, _bob, bud_id = await _bud(pg_session_factory)

    assert await _weights(pg_session_factory, org, bud_id, None) == {}
