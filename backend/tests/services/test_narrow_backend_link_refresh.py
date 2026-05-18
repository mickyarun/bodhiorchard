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

"""Behavioural tests for the narrow backend-link refresh.

End-to-end-shape rather than statement-shape: we drive the real
``extract_api_paths`` + ``bucket_per_repo`` machinery against a
fixture frontend repo on disk + a small in-memory :class:`BackendIndex`,
mocking only the DB-edge calls (``FeatureRepository``, etc.) so the
test stays hermetic.

Three slices:

1. **Linked path** — feature whose seed file fetches a route the
   index declares → ``replace_backend_links`` called with the matched
   tuple, ``clear`` not called.
2. **No-match path** — feature whose seed file fetches a path the
   index doesn't declare → ``clear_backend_links_with_trace`` called.
3. **Skipped path** — feature without a PRIMARY junction → no DB
   writes; only the skip counter ticks.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.scan.backend_link import narrow_refresh
from app.services.scan.backend_link.backend_indexer import BackendIndex
from app.services.scan.backend_link.narrow_refresh import (
    refresh_backend_links_for_features,
)


@pytest.fixture
def backend_repo_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def frontend_repo_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def feature_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def index(backend_repo_id: uuid.UUID) -> BackendIndex:
    """In-memory index declaring ``/api/users`` in one backend file."""
    idx = BackendIndex()
    entry = (backend_repo_id, "src/users/router.py")
    idx.paths["/api/users"] = {entry}
    idx.suffix_paths["/api/users"] = {entry}
    idx.suffix_paths["/users"] = {entry}
    return idx


@pytest.fixture
def frontend_dir(tmp_path: Path) -> Path:
    """Frontend worktree containing one .ts file that fetches ``/api/users``."""
    src = tmp_path / "src" / "stores"
    src.mkdir(parents=True)
    (src / "users.ts").write_text(
        "export const fetchUsers = () => fetch('/api/users');\n",
        encoding="utf-8",
    )
    return tmp_path


def _make_feature(feature_id: uuid.UUID, title: str = "Users feature") -> MagicMock:
    feat = MagicMock()
    feat.id = feature_id
    feat.feature_title = title
    feat.is_active = True
    return feat


def _make_primary_link(
    feature_id: uuid.UUID,
    frontend_repo_id: uuid.UUID,
    files: list[str],
) -> MagicMock:
    link = MagicMock()
    link.feature_id = feature_id
    link.repo_id = frontend_repo_id
    link.code_locations = {"frontend": files}
    return link


def _make_repo(repo_id: uuid.UUID, repo_path: Path) -> MagicMock:
    repo = MagicMock()
    repo.id = repo_id
    repo.path = str(repo_path)
    repo.name = "frontend-test"
    return repo


def _patch_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    index: BackendIndex,
    feature: MagicMock | None,
    primary_link: MagicMock | None,
    frontend_repo: MagicMock | None,
) -> dict[str, Any]:
    """Wire the module's external dependencies to controllable stubs.

    Returns a captures dict the test can introspect.
    """
    captures: dict[str, Any] = {"replace_calls": [], "clear_calls": []}

    async def fake_build_index(_db: Any, *, org_id: Any) -> tuple[BackendIndex, list[Any]]:
        del org_id
        return index, []

    async def fake_replace_backend_links(_db: Any, **kwargs: Any) -> None:
        captures["replace_calls"].append(kwargs)

    async def fake_clear(_db: Any, **kwargs: Any) -> None:
        captures["clear_calls"].append(kwargs)

    feat_repo = MagicMock()
    feat_repo.get_by_id = AsyncMock(return_value=feature)
    feat_repo.find_primary_link = AsyncMock(return_value=primary_link)

    tracked_repo = MagicMock()
    tracked_repo.get_by_id = AsyncMock(return_value=frontend_repo)

    monkeypatch.setattr(narrow_refresh, "build_backend_index_from_cache", fake_build_index)
    monkeypatch.setattr(narrow_refresh, "replace_backend_links", fake_replace_backend_links)
    monkeypatch.setattr(narrow_refresh, "clear_backend_links_with_trace", fake_clear)
    return captures, feat_repo, tracked_repo


@pytest.mark.asyncio
async def test_refresh_links_a_matching_feature(
    monkeypatch: pytest.MonkeyPatch,
    org_id: uuid.UUID,
    feature_id: uuid.UUID,
    frontend_repo_id: uuid.UUID,
    backend_repo_id: uuid.UUID,
    index: BackendIndex,
    frontend_dir: Path,
) -> None:
    feature = _make_feature(feature_id)
    primary = _make_primary_link(feature_id, frontend_repo_id, ["src/stores/users.ts"])
    frontend = _make_repo(frontend_repo_id, frontend_dir)
    captures, feat_repo, tracked_repo = _patch_dependencies(
        monkeypatch,
        index=index,
        feature=feature,
        primary_link=primary,
        frontend_repo=frontend,
    )
    db = MagicMock()
    db.commit = AsyncMock()

    with (
        patch.object(narrow_refresh, "FeatureRepository", return_value=feat_repo),
        patch.object(narrow_refresh, "TrackedRepoRepository", return_value=tracked_repo),
    ):
        result = await refresh_backend_links_for_features(
            db, org_id=org_id, feature_ids=[feature_id]
        )

    assert result.processed == 1
    assert result.linked == 1
    assert result.cleared == 0
    assert len(captures["replace_calls"]) == 1
    call = captures["replace_calls"][0]
    assert call["feature_id"] == feature_id
    repos = dict((rid, paths) for rid, paths, _files in call["backend_repos"])
    assert backend_repo_id in repos
    assert "/api/users" in repos[backend_repo_id]


@pytest.mark.asyncio
async def test_refresh_clears_when_no_index_match(
    monkeypatch: pytest.MonkeyPatch,
    org_id: uuid.UUID,
    feature_id: uuid.UUID,
    frontend_repo_id: uuid.UUID,
    index: BackendIndex,
    tmp_path: Path,
) -> None:
    """Frontend fetches a path the index doesn't know — clear stale links."""
    src = tmp_path / "src" / "stores"
    src.mkdir(parents=True)
    (src / "ghosts.ts").write_text(
        "export const fetchGhosts = () => fetch('/api/ghosts');\n",
        encoding="utf-8",
    )

    feature = _make_feature(feature_id, "Ghost finder")
    primary = _make_primary_link(feature_id, frontend_repo_id, ["src/stores/ghosts.ts"])
    frontend = _make_repo(frontend_repo_id, tmp_path)
    captures, feat_repo, tracked_repo = _patch_dependencies(
        monkeypatch,
        index=index,
        feature=feature,
        primary_link=primary,
        frontend_repo=frontend,
    )
    db = MagicMock()
    db.commit = AsyncMock()

    with (
        patch.object(narrow_refresh, "FeatureRepository", return_value=feat_repo),
        patch.object(narrow_refresh, "TrackedRepoRepository", return_value=tracked_repo),
    ):
        result = await refresh_backend_links_for_features(
            db, org_id=org_id, feature_ids=[feature_id]
        )

    assert result.processed == 1
    assert result.linked == 0
    assert result.cleared == 1
    assert result.no_index_matches == 1
    assert len(captures["clear_calls"]) == 1
    assert captures["clear_calls"][0]["reason"] == "narrow_no_index_matches"


@pytest.mark.asyncio
async def test_refresh_skips_features_without_primary_link(
    monkeypatch: pytest.MonkeyPatch,
    org_id: uuid.UUID,
    feature_id: uuid.UUID,
    index: BackendIndex,
) -> None:
    captures, feat_repo, tracked_repo = _patch_dependencies(
        monkeypatch,
        index=index,
        feature=_make_feature(feature_id),
        primary_link=None,  # no PRIMARY junction
        frontend_repo=None,
    )
    db = MagicMock()
    db.commit = AsyncMock()

    with (
        patch.object(narrow_refresh, "FeatureRepository", return_value=feat_repo),
        patch.object(narrow_refresh, "TrackedRepoRepository", return_value=tracked_repo),
    ):
        result = await refresh_backend_links_for_features(
            db, org_id=org_id, feature_ids=[feature_id]
        )

    assert result.processed == 0
    assert result.skipped_no_primary == 1
    assert captures["replace_calls"] == []
    assert captures["clear_calls"] == []


@pytest.mark.asyncio
async def test_refresh_returns_empty_result_for_empty_input(
    monkeypatch: pytest.MonkeyPatch,
    org_id: uuid.UUID,
    index: BackendIndex,
) -> None:
    """No feature_ids → no DB writes, no index build."""
    build_called = False

    async def fake_build_index(_db: Any, *, org_id: Any) -> tuple[BackendIndex, list[Any]]:
        nonlocal build_called
        build_called = True
        return index, []

    monkeypatch.setattr(narrow_refresh, "build_backend_index_from_cache", fake_build_index)
    db = MagicMock()
    db.commit = AsyncMock()

    result = await refresh_backend_links_for_features(db, org_id=org_id, feature_ids=[])

    assert result.processed == 0
    assert build_called is False  # short-circuited before the index build
