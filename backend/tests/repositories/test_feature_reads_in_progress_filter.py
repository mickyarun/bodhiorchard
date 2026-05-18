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

"""Statement-shape tests for the ``view_mode`` filter on the Features tab.

The Features API exposes four exclusive view modes (``all`` / ``active``
/ ``in_progress`` / ``deactivated``). Each maps to a distinct WHERE
clause shape on ``list_with_links`` and ``count_with_links``. These
tests pin the predicate for each mode without spinning up Postgres —
they assert against the compiled SQL string the repo emits.

Two contracts are load-bearing:

1. The ``active`` mode's ``feature_status NOT IN (...)`` predicate
   must be wrapped in ``OR feature_status IS NULL`` so scan-authored
   rows (the bulk today) stay visible. SQL three-valued logic would
   otherwise drop them silently.
2. ``count_with_links`` must apply the same view-mode predicate as
   ``list_with_links`` — divergence would break the paginator.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.feature_reads import FeatureReadRepository


def _make_db() -> MagicMock:
    """Build an async-session double that records the SQL passed to execute."""
    db = MagicMock()
    result = MagicMock()
    result.scalars = MagicMock(return_value=MagicMock(unique=lambda: MagicMock(all=lambda: [])))
    result.scalar_one = MagicMock(return_value=0)
    db.execute = AsyncMock(return_value=result)
    return db


def _compiled_sql(call_args: Any) -> str:
    """Pull the SQL text out of a captured ``db.execute`` invocation."""
    stmt = call_args.args[0]
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


# --- list_with_links view modes ----------------------------------------------


def _has_status_predicate(sql: str) -> bool:
    """True iff the SQL filters on ``feature_status``.

    Searches only for predicate forms (``feature_status NOT IN``,
    ``feature_status IN``, ``feature_status IS NULL``) — the column
    name itself appears in the SELECT list whenever we ``select(Feature)``
    because every column gets projected. A naive ``in sql`` check
    would falsely flag those.
    """
    return (
        "feature_status NOT IN" in sql
        or "feature_status IN" in sql
        or "feature_status IS NULL" in sql
    )


@pytest.mark.asyncio
async def test_mode_all_is_default_and_emits_only_is_active_predicate() -> None:
    """The default view shows every active row regardless of status —
    no ``feature_status`` predicate, only ``is_active=true``.
    """
    db = _make_db()
    repo = FeatureReadRepository(db, org_id=uuid.uuid4())

    await repo.list_with_links()  # no view_mode passed → default 'all'

    sql = _compiled_sql(db.execute.call_args)
    assert "features.is_active IS true" in sql
    assert not _has_status_predicate(sql)


@pytest.mark.asyncio
async def test_mode_active_excludes_in_progress_statuses() -> None:
    """``active`` keeps live rows (NULL or implemented) and drops the
    BUD work-in-progress statuses.

    The NULL branch is critical — without it, three-valued SQL drops
    every scan-authored row.
    """
    db = _make_db()
    repo = FeatureReadRepository(db, org_id=uuid.uuid4())

    await repo.list_with_links(view_mode="active")

    sql = _compiled_sql(db.execute.call_args)
    assert "features.is_active IS true" in sql
    assert "feature_status IS NULL" in sql
    assert "feature_status NOT IN" in sql
    assert "'in_progress'" in sql
    assert "'planned'" in sql


@pytest.mark.asyncio
async def test_mode_in_progress_filters_to_bud_lifecycle_statuses_only() -> None:
    """``in_progress`` is the inverse of ``active``: positive filter
    on ``feature_status IN ('planned','in_progress')``.
    """
    db = _make_db()
    repo = FeatureReadRepository(db, org_id=uuid.uuid4())

    await repo.list_with_links(view_mode="in_progress")

    sql = _compiled_sql(db.execute.call_args)
    assert "features.is_active IS true" in sql
    assert "feature_status IN" in sql
    assert "'in_progress'" in sql
    assert "'planned'" in sql
    # Must NOT have the NULL fallback — that's the ``active`` mode's
    # job. NULL rows are deliberately excluded from the in-progress
    # surface (scan-authored rows aren't BUD work).
    assert "feature_status IS NULL" not in sql


@pytest.mark.asyncio
async def test_mode_deactivated_filters_to_soft_deleted_only() -> None:
    """``deactivated`` shows ONLY soft-deleted rows, regardless of
    ``feature_status``. The page becomes an audit surface for the
    operator.
    """
    db = _make_db()
    repo = FeatureReadRepository(db, org_id=uuid.uuid4())

    await repo.list_with_links(view_mode="deactivated")

    sql = _compiled_sql(db.execute.call_args)
    assert "features.is_active IS false" in sql
    # No status predicate — deactivated rows of any kind are surfaced.
    assert not _has_status_predicate(sql)


@pytest.mark.asyncio
async def test_unknown_mode_falls_back_to_all_safely() -> None:
    """Unknown ``view_mode`` strings (e.g. typo, future-client) fall
    through to ``all`` rather than emptying the page. "Better too
    much than nothing" is the safest default for a presentational
    surface.
    """
    db = _make_db()
    repo = FeatureReadRepository(db, org_id=uuid.uuid4())

    await repo.list_with_links(view_mode="nonsense_mode_42")

    sql = _compiled_sql(db.execute.call_args)
    assert "features.is_active IS true" in sql
    assert not _has_status_predicate(sql)


# --- count_with_links mirrors list_with_links --------------------------------


@pytest.mark.asyncio
async def test_count_with_links_mirrors_active_filter() -> None:
    """``count_with_links`` must apply the same view-mode predicate
    or the page total disagrees with the visible row count and the
    paginator breaks.
    """
    db = _make_db()
    repo = FeatureReadRepository(db, org_id=uuid.uuid4())

    await repo.count_with_links(view_mode="active")

    sql = _compiled_sql(db.execute.call_args)
    assert "feature_status IS NULL" in sql
    assert "feature_status NOT IN" in sql


@pytest.mark.asyncio
async def test_count_with_links_mirrors_in_progress_filter() -> None:
    db = _make_db()
    repo = FeatureReadRepository(db, org_id=uuid.uuid4())

    await repo.count_with_links(view_mode="in_progress")

    sql = _compiled_sql(db.execute.call_args)
    assert "feature_status IN" in sql
    assert "'in_progress'" in sql


@pytest.mark.asyncio
async def test_count_with_links_mirrors_deactivated_filter() -> None:
    db = _make_db()
    repo = FeatureReadRepository(db, org_id=uuid.uuid4())

    await repo.count_with_links(view_mode="deactivated")

    sql = _compiled_sql(db.execute.call_args)
    assert "features.is_active IS false" in sql
