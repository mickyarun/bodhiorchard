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

"""Tests for :meth:`TrackedRepoRepository.get_scanned_status_by_ids`.

The repo split between full-scan and rescan paths is anchored on
``last_scanned_at`` — if this helper miscategorises a repo, the API
either re-runs an expensive full scan that wasn't needed or attempts
a diff against a non-existent base. The dict-shape assertions guard
against quiet refactors.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.tracked_repository import TrackedRepoRepository


def _row(repo_id: uuid.UUID, last_scanned_at: datetime | None) -> MagicMock:
    row = MagicMock()
    row.id = repo_id
    row.last_scanned_at = last_scanned_at
    return row


@pytest.mark.asyncio
async def test_returns_empty_dict_for_empty_input() -> None:
    """An empty id list must short-circuit without hitting the DB."""
    db = MagicMock()
    db.execute = AsyncMock()
    repo = TrackedRepoRepository(db, org_id=uuid.uuid4())

    result = await repo.get_scanned_status_by_ids([])

    assert result == {}
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_maps_last_scanned_at_to_bool() -> None:
    """Non-null timestamp → True; NULL → False."""
    db = MagicMock()
    scanned_id = uuid.uuid4()
    fresh_id = uuid.uuid4()
    execute_result = MagicMock()
    execute_result.all = MagicMock(
        return_value=[
            _row(scanned_id, datetime(2026, 1, 1, tzinfo=UTC)),
            _row(fresh_id, None),
        ]
    )
    db.execute = AsyncMock(return_value=execute_result)
    repo = TrackedRepoRepository(db, org_id=uuid.uuid4())

    result = await repo.get_scanned_status_by_ids([scanned_id, fresh_id])

    assert result == {scanned_id: True, fresh_id: False}


@pytest.mark.asyncio
async def test_omits_ids_filtered_by_org_scope() -> None:
    """An id absent from the result set means the org can't see that repo.

    The caller uses absence to fall through to a 404 — verify the
    dict simply omits the id rather than mapping it to a default.
    """
    db = MagicMock()
    visible_id = uuid.uuid4()
    invisible_id = uuid.uuid4()  # the org doesn't own this repo
    execute_result = MagicMock()
    execute_result.all = MagicMock(
        return_value=[_row(visible_id, datetime(2026, 1, 1, tzinfo=UTC))]
    )
    db.execute = AsyncMock(return_value=execute_result)
    repo = TrackedRepoRepository(db, org_id=uuid.uuid4())

    result = await repo.get_scanned_status_by_ids([visible_id, invisible_id])

    assert visible_id in result
    assert invisible_id not in result


@pytest.mark.asyncio
async def test_sql_filters_on_id_in_clause() -> None:
    """The SELECT must IN-filter on the supplied repo_ids so the org
    scope can't be widened by a careless future refactor.
    """
    db = MagicMock()
    db.execute = AsyncMock(return_value=_empty_result())
    repo = TrackedRepoRepository(db, org_id=uuid.uuid4())
    target_ids = [uuid.uuid4(), uuid.uuid4()]

    await repo.get_scanned_status_by_ids(target_ids)

    stmt = db.execute.call_args.args[0]
    compiled = stmt.compile(compile_kwargs={"literal_binds": False})
    sql = str(compiled).lower()
    assert "tracked_repositories" in sql
    assert "last_scanned_at" in sql
    assert "id in" in sql


def _empty_result() -> MagicMock:
    result: Any = MagicMock()
    result.all = MagicMock(return_value=[])
    return result
