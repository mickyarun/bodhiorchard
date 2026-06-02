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

"""Predicate-shape tests for ``list_open_for_bud_with_repo``.

The OR-of-equalities form that used to live here let through PRs linked
to a *different* BUD on the same impacted repo — the over-matching bug
this PR fixes. These tests pin the corrected predicate:

* ``bud_id == X`` — directly linked PRs.
* ``bud_id IS NULL AND repo_id IN impacted`` — aggregate release PRs
  (``develop → main``) that legitimately carry no single owning BUD.

Asserting against the compiled SQL keeps the regression visible at the
predicate level without needing a live Postgres in CI.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.pull_request import PullRequestRepository


def _make_db_capturing_stmt() -> tuple[MagicMock, list[object]]:
    """Return a DB mock that records the statement objects it executes."""
    captured: list[object] = []

    async def _execute(stmt: object) -> MagicMock:
        captured.append(stmt)
        tuples_mock = MagicMock()
        tuples_mock.all = MagicMock(return_value=[])
        result = MagicMock()
        result.tuples = MagicMock(return_value=tuples_mock)
        return result

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_execute)
    return db, captured


def _compiled_sql(stmt: object) -> str:
    """Compile a SQLAlchemy Core/ORM statement to a SQL string."""
    compiled = stmt.compile(compile_kwargs={"literal_binds": False})  # type: ignore[attr-defined]
    return str(compiled)


@pytest.mark.asyncio
async def test_predicate_without_impacted_repos_is_bud_id_equality_only() -> None:
    """When no impacted-repo fallback is requested, only direct links return."""
    db, captured = _make_db_capturing_stmt()
    repo = PullRequestRepository(db, org_id=uuid.uuid4())

    await repo.list_open_for_bud_with_repo(uuid.uuid4(), impacted_repo_ids=None)

    sql = _compiled_sql(captured[0])
    assert "pull_requests.bud_id =" in sql
    # The repo_id IN clause must not appear when no impacted repos are passed.
    assert "pull_requests.repo_id IN" not in sql
    # The IS NULL release-PR escape hatch must also be absent — without
    # impacted_repo_ids there is no anchor for an "unlinked PR on this repo"
    # to legitimately surface, so the predicate should be a clean equality.
    assert "pull_requests.bud_id IS NULL" not in sql


@pytest.mark.asyncio
async def test_predicate_with_impacted_repos_is_three_way() -> None:
    """Impacted-repo fallback must require ``bud_id IS NULL`` to fire.

    A plain ``OR(bud_id == X, repo_id IN ...)`` was the over-matching bug.
    The corrected shape is ``bud_id == X OR (bud_id IS NULL AND repo_id IN ...)``
    so PRs linked to another BUD on the same impacted repo are excluded.
    """
    db, captured = _make_db_capturing_stmt()
    repo = PullRequestRepository(db, org_id=uuid.uuid4())

    await repo.list_open_for_bud_with_repo(
        uuid.uuid4(), impacted_repo_ids=[uuid.uuid4(), uuid.uuid4()]
    )

    sql = _compiled_sql(captured[0])
    # Direct-link arm.
    assert "pull_requests.bud_id =" in sql
    # Release-PR arm: NULL-gate AND repo membership.
    assert "pull_requests.bud_id IS NULL" in sql
    assert "pull_requests.repo_id IN" in sql
    # Glued by AND inside, OR outside.
    upper = sql.upper()
    assert " OR " in upper
    assert " AND " in upper


@pytest.mark.asyncio
async def test_state_filter_is_always_open() -> None:
    """Closed and merged PRs are never returned by this method."""
    db, captured = _make_db_capturing_stmt()
    repo = PullRequestRepository(db, org_id=uuid.uuid4())

    await repo.list_open_for_bud_with_repo(uuid.uuid4(), impacted_repo_ids=[uuid.uuid4()])

    sql = _compiled_sql(captured[0])
    assert "pull_requests.state" in sql
