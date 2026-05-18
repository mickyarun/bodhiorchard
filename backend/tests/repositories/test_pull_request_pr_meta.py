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

"""Statement-shape tests for ``map_shas_to_pr_meta``.

The method is a thin SQL wrapper; these tests pin (a) the short-
circuit on empty input, (b) the filter shape (``IN``-list +
non-null PR number predicate), and (c) the result-row → dict
conversion.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.pull_request import PullRequestRepository


def _row(sha: str, pr_number: int, html_url: str | None) -> MagicMock:
    """Build a row-tuple-like that ``result.all()`` would yield."""
    return (sha, pr_number, html_url)


def _make_db(rows: list[tuple[str, int, str | None]]) -> MagicMock:
    db = MagicMock()
    all_mock = MagicMock(return_value=rows)
    result = MagicMock()
    result.all = all_mock
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_map_shas_short_circuits_on_empty_input() -> None:
    """No SHAs → no DB hit. Important so per-page hot path is cheap."""
    db = MagicMock()
    db.execute = AsyncMock()
    repo = PullRequestRepository(db, org_id=uuid.uuid4())

    out = await repo.map_shas_to_pr_meta([])

    assert out == {}
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_map_shas_returns_sha_to_pr_meta_dict() -> None:
    """Valid rows → ``{sha: (pr_number, html_url)}`` shape."""
    rows = [
        _row("sha-a", 42, "https://github.com/x/y/pull/42"),
        _row("sha-b", 43, None),  # html_url can be null on legacy rows
    ]
    db = _make_db(rows)
    repo = PullRequestRepository(db, org_id=uuid.uuid4())

    out = await repo.map_shas_to_pr_meta(["sha-a", "sha-b"])

    assert out == {
        "sha-a": (42, "https://github.com/x/y/pull/42"),
        "sha-b": (43, None),
    }
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_map_shas_drops_rows_with_null_pr_number() -> None:
    """Rows where ``github_pr_number`` is null (data-integrity edge case)
    must be silently filtered out rather than raising.
    """
    rows: list[tuple[str, int | None, str | None]] = [
        _row("good", 7, "url"),
        ("orphan", None, None),  # pretend pr_number came back null
    ]
    db = _make_db(rows)
    repo = PullRequestRepository(db, org_id=uuid.uuid4())

    out = await repo.map_shas_to_pr_meta(["good", "orphan"])

    assert out == {"good": (7, "url")}


@pytest.mark.asyncio
async def test_map_shas_query_filters_by_in_list_and_nonnull_pr() -> None:
    """SQL must restrict to (sha IN :shas, pr_number IS NOT NULL).
    Catches a refactor that drops the non-null guard and starts
    returning open-PR rows (which have no ``merge_commit_sha`` yet but
    do have a ``github_pr_number``) — those would never match a SHA
    anyway, but the predicate guards against future shape changes.
    """
    db = _make_db([])
    repo = PullRequestRepository(db, org_id=uuid.uuid4())

    await repo.map_shas_to_pr_meta(["x"])

    sent_stmt: Any = db.execute.call_args.args[0]
    sent_text = str(sent_stmt)
    assert "merge_commit_sha IN" in sent_text
    assert "github_pr_number IS NOT NULL" in sent_text
