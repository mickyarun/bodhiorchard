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

"""Tests for ``handlers_hooks._resolve_repo_id``.

The hook script in a developer's tracked repo sends ``repo_path`` as the
absolute path on the developer's laptop. ``tracked_repositories.path``
stores the server-side clone path, so exact equality only works when
both run on the same host. The resolver must fall back to basename →
``get_by_name`` so cross-host developers still get their repo wired up
to a tracked row — otherwise downstream consumers (the multiplayer
walk-to-tree sim, the dashboard file/commit counters) receive
``repo_name = None`` and silently skip the event.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp.handlers_hooks import _resolve_repo_id


@pytest.mark.asyncio
async def test_returns_none_for_empty_path() -> None:
    """Empty path must short-circuit without hitting the DB."""
    db = MagicMock()
    result = await _resolve_repo_id(db, uuid.uuid4(), "")
    assert result is None


@pytest.mark.asyncio
async def test_exact_path_match_wins() -> None:
    """When the path matches a tracked row verbatim, basename is not consulted."""
    org_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    tracked = MagicMock(id=repo_id)

    with patch("app.mcp.handlers_hooks.TrackedRepoRepository") as mock_repo:
        instance = mock_repo.return_value
        instance.get_by_path = AsyncMock(return_value=tracked)
        instance.get_by_name = AsyncMock()

        result = await _resolve_repo_id(MagicMock(), org_id, "/srv/repos/taskflow-web")

    assert result == repo_id
    instance.get_by_path.assert_awaited_once_with("/srv/repos/taskflow-web")
    instance.get_by_name.assert_not_awaited()


@pytest.mark.asyncio
async def test_falls_back_to_basename_when_path_misses() -> None:
    """The cross-host case: dev's laptop path doesn't match, basename does."""
    org_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    tracked = MagicMock(id=repo_id)

    with patch("app.mcp.handlers_hooks.TrackedRepoRepository") as mock_repo:
        instance = mock_repo.return_value
        instance.get_by_path = AsyncMock(return_value=None)
        instance.get_by_name = AsyncMock(return_value=tracked)

        result = await _resolve_repo_id(
            MagicMock(), org_id, "/Users/alice/code/example-bodhiorchard/taskflow-web"
        )

    assert result == repo_id
    instance.get_by_name.assert_awaited_once_with("taskflow-web")


@pytest.mark.asyncio
async def test_returns_none_when_neither_path_nor_name_matches() -> None:
    """If both lookups miss, downstream gets a clean None (no exception)."""
    with patch("app.mcp.handlers_hooks.TrackedRepoRepository") as mock_repo:
        instance = mock_repo.return_value
        instance.get_by_path = AsyncMock(return_value=None)
        instance.get_by_name = AsyncMock(return_value=None)

        result = await _resolve_repo_id(MagicMock(), uuid.uuid4(), "/tmp/unknown-repo")

    assert result is None


@pytest.mark.asyncio
async def test_trailing_slash_in_path_does_not_break_basename() -> None:
    """``/foo/bar/`` → basename ``bar`` (rstrip before basename)."""
    org_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    tracked = MagicMock(id=repo_id)

    with patch("app.mcp.handlers_hooks.TrackedRepoRepository") as mock_repo:
        instance = mock_repo.return_value
        instance.get_by_path = AsyncMock(return_value=None)
        instance.get_by_name = AsyncMock(return_value=tracked)

        result = await _resolve_repo_id(MagicMock(), org_id, "/Users/alice/taskflow-web/")

    assert result == repo_id
    instance.get_by_name.assert_awaited_once_with("taskflow-web")
