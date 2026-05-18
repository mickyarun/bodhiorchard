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

"""Unit tests for the shared cluster-index helper.

The helper is the dispatcher's pre-step on the PR-merge narrow path:
ensure ``cluster_cache`` rows exist for the merge SHA before computing
affected clusters. Without it, the narrow path is structurally
unreachable (the merge commit never has prior cache rows).

These tests cover orchestration only — the indexer, worktree refresh,
and DB writer are stubbed via monkeypatch so the cases run fast and
don't need a real repo on disk.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest

from app.services.scan import cluster_index


@pytest.fixture
def fake_indexer_success(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace every collaborator with success-path stubs.

    Returns a dict the test can inspect to verify what got called with
    what args.
    """
    captured: dict[str, Any] = {
        "main_branch_for": None,
        "worktree_args": None,
        "rev_parse_path": None,
        "indexed_path": None,
        "indexed_sha": None,
        "persist_args": None,
    }

    async def _detect(path: str) -> str:
        captured["main_branch_for"] = path
        return "main"

    @asynccontextmanager
    async def _session(_org_id: uuid.UUID) -> Any:
        class _Org:
            pass

        class _SessionLike:
            async def execute(self, *_a: Any, **_kw: Any) -> Any:
                return None

        yield _SessionLike()

    class _OrgRepoFake:
        def __init__(self, db: Any) -> None:
            self._db = db

        async def get_by_id(self, _id: uuid.UUID) -> Any:
            return object()

    async def _ensure_worktree(
        repo_path: str, main_branch: str, *, skip_fetch: bool, org: Any
    ) -> str:
        captured["worktree_args"] = (repo_path, main_branch, skip_fetch)
        return f"/tmp/scan-worktrees/{Path(repo_path).name}/{main_branch}"

    async def _run_git(args: list[str], *, cwd: str) -> tuple[str, str, int]:
        captured["rev_parse_path"] = cwd
        assert args == ["rev-parse", "HEAD"]
        return ("resolvedsha1234567890abcdef1234567890abcdef12", "", 0)

    class _FakeIndexResult:
        def __init__(self) -> None:
            class _Cluster:
                def __init__(self, cid: str) -> None:
                    self.cluster_id = cid
                    self.label = f"label-{cid}"
                    self.symbol_count = 3
                    self.cohesion = 0.5
                    self.files = [f"src/{cid}.py"]
                    self.symbols: list[str] = []
                    self.signature = f"sig-{cid}"

            self.success = True
            self.error = None
            self.elapsed_s = 1.23
            self.clusters = [_Cluster("c0"), _Cluster("c1")]
            self.graph = None
            self.file_count = 4

    async def _index(path: str, *, head_sha: str, max_files: int) -> _FakeIndexResult:
        captured["indexed_path"] = path
        captured["indexed_sha"] = head_sha
        captured["indexed_max_files"] = max_files
        return _FakeIndexResult()

    async def _persist(
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID,
        head_sha: str,
        result: Any,
    ) -> tuple[int, bool, str | None, str | None]:
        captured["persist_args"] = {
            "org_id": org_id,
            "repo_id": repo_id,
            "head_sha": head_sha,
            "cluster_count": len(result.clusters),
        }
        return (len(result.clusters), False, None, None)

    monkeypatch.setattr(cluster_index, "_detect_main_branch", _detect)
    monkeypatch.setattr(cluster_index, "with_session", _session)
    monkeypatch.setattr(cluster_index, "OrganizationRepository", _OrgRepoFake)
    monkeypatch.setattr(cluster_index, "ensure_scan_test_worktree", _ensure_worktree)
    monkeypatch.setattr(cluster_index, "run_git", _run_git)
    monkeypatch.setattr(cluster_index, "index_repo", _index)
    monkeypatch.setattr(cluster_index, "persist_index_result", _persist)

    return captured


async def test_index_and_cache_happy_path(fake_indexer_success: dict[str, Any]) -> None:
    """Success path: returns the count of cluster_cache rows written."""
    org_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    rows = await cluster_index.index_and_cache(
        org_id=org_id,
        repo_id=repo_id,
        repo_path="/tmp/repo",
        head_sha="abc12345",
    )
    assert rows == 2  # two fake clusters
    persist = fake_indexer_success["persist_args"]
    assert persist["org_id"] == org_id
    assert persist["repo_id"] == repo_id
    assert persist["head_sha"] == "abc12345"
    # The indexer received the override SHA, not a re-detected one.
    assert fake_indexer_success["indexed_sha"] == "abc12345"
    assert fake_indexer_success["rev_parse_path"] is None
    # ``_detect_main_branch`` was called against the source repo path.
    assert fake_indexer_success["main_branch_for"] == "/tmp/repo"
    # ``ensure_scan_test_worktree`` got the resolved main_branch + the
    # default ``skip_fetch=False`` we documented as the safe default.
    repo_arg, branch_arg, skip_fetch_arg = fake_indexer_success["worktree_args"]
    assert repo_arg == "/tmp/repo"
    assert branch_arg == "main"
    assert skip_fetch_arg is False


async def test_index_and_cache_resolves_head_when_none(
    fake_indexer_success: dict[str, Any],
) -> None:
    """When ``head_sha=None`` the helper reads ``HEAD`` from the worktree."""
    await cluster_index.index_and_cache(
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        repo_path="/tmp/repo",
        head_sha=None,
    )
    # The rev-parse fake returned ``resolvedsha1234567890abcdef...``.
    assert fake_indexer_success["indexed_sha"].startswith("resolvedsha")
    persist_sha = fake_indexer_success["persist_args"]["head_sha"]
    assert persist_sha.startswith("resolvedsha")
    # CRITICAL: rev-parse must run against the *worktree*, not the source
    # repo. The worktree is what's been reset to ``origin/<main>``; the
    # source-repo HEAD could be on any feature branch in a dev loop.
    rev_parse_cwd = fake_indexer_success["rev_parse_path"]
    assert rev_parse_cwd.endswith("/scan-worktrees/repo/main")


async def test_index_and_cache_forwards_skip_fetch_to_worktree(
    fake_indexer_success: dict[str, Any],
) -> None:
    """``skip_fetch=True`` reuses the worktree as-is — no network round-trip.

    Used on the PR-merge hot path: the webhook handler often already has
    the merge SHA on disk, so the dispatcher pre-step can elide the
    fetch. Coverage: prove the kwarg flows through to
    ``ensure_scan_test_worktree`` rather than being silently dropped.
    """
    await cluster_index.index_and_cache(
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        repo_path="/tmp/repo",
        head_sha="abc12345",
        skip_fetch=True,
    )
    _repo, _branch, skip_fetch_arg = fake_indexer_success["worktree_args"]
    assert skip_fetch_arg is True


async def test_index_and_cache_raises_on_indexer_failure(
    monkeypatch: pytest.MonkeyPatch, fake_indexer_success: dict[str, Any]
) -> None:
    """Indexer ``success=False`` must propagate as ``RuntimeError``.

    Callers (the dispatcher) catch and fall through to the existing
    full-scan fallback — the bug it'd hide is the indexer silently
    leaving cluster_cache empty.
    """

    class _FailingIndexResult:
        success = False
        error = "synthetic indexer failure"
        elapsed_s = 0.0
        clusters: list[Any] = []
        graph = None

    async def _failing(*_a: Any, **_kw: Any) -> _FailingIndexResult:
        return _FailingIndexResult()

    monkeypatch.setattr(cluster_index, "index_repo", _failing)
    with pytest.raises(RuntimeError, match="indexer failed"):
        await cluster_index.index_and_cache(
            org_id=uuid.uuid4(),
            repo_id=uuid.uuid4(),
            repo_path="/tmp/repo",
            head_sha="abc12345",
        )


async def test_index_and_cache_raises_on_cluster_cache_error(
    monkeypatch: pytest.MonkeyPatch, fake_indexer_success: dict[str, Any]
) -> None:
    """If the cluster_cache write fails, the helper must raise.

    Returning silently would defeat the whole point of the pre-step —
    the dispatcher needs to know the cache wasn't populated so it can
    fall back. ``persist_index_result`` already swallows DB exceptions
    and returns an error string; we re-raise from ``index_and_cache``.
    """

    async def _persist_with_error(**_kw: Any) -> tuple[int, bool, str | None, str | None]:
        return (0, False, "OperationalError", None)

    monkeypatch.setattr(cluster_index, "persist_index_result", _persist_with_error)
    with pytest.raises(RuntimeError, match="cluster_cache write failed"):
        await cluster_index.index_and_cache(
            org_id=uuid.uuid4(),
            repo_id=uuid.uuid4(),
            repo_path="/tmp/repo",
            head_sha="abc12345",
        )


async def test_index_and_cache_raises_when_no_main_branch(
    monkeypatch: pytest.MonkeyPatch, fake_indexer_success: dict[str, Any]
) -> None:
    """``_detect_main_branch`` returning falsy means the repo is broken."""

    async def _no_branch(_path: str) -> str:
        return ""

    monkeypatch.setattr(cluster_index, "_detect_main_branch", _no_branch)
    with pytest.raises(RuntimeError, match="cannot detect main branch"):
        await cluster_index.index_and_cache(
            org_id=uuid.uuid4(),
            repo_id=uuid.uuid4(),
            repo_path="/tmp/repo",
            head_sha="abc12345",
        )
