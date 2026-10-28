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

"""The ingest stage's cache short-circuit.

A cache hit for the worktree's HEAD must not run the indexer. When the
indexer cache is fresh but synthesis output is missing, indexing stays
skipped yet the reduction chain is forced so synthesis sees communities.
A miss runs the indexer and persists under that HEAD. Git, the worktree,
the indexer and the database are all faked.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import networkx as nx
import pytest

from app.services.scan.stages import StageContext
from app.services.scan.stages import ingest as stage
from app.services.scan.stages._skip_predicates import SkipDecision

HEAD = "c0ffee" + "0" * 34
CTX = StageContext(run_id="r", repo_path="/repo", repo_name="web")


@dataclass
class _World:
    """What the stage asked of the indexer and the cache writer."""

    indexed: list[str] = field(default_factory=list)
    persisted: list[str] = field(default_factory=list)


def _wire(monkeypatch: pytest.MonkeyPatch, *, cache_hit: bool, synth_present: bool) -> _World:
    world = _World()

    @asynccontextmanager
    async def _session(_org: uuid.UUID) -> Any:
        yield SimpleNamespace()

    class _Orgs:
        def __init__(self, db: Any) -> None:
            pass

        async def get_by_id(self, org_id: uuid.UUID) -> object:
            return SimpleNamespace(id=org_id)

    async def _worktree(path: str, branch: str, **kw: Any) -> str:
        return "/worktrees/web/main"

    async def _git(args: list[str], cwd: str) -> tuple[str, str, int]:
        return f"{HEAD}\n", "", 0

    async def _skip_indexing(db: Any, **kw: Any) -> SkipDecision:
        assert kw["head_sha"] == HEAD
        if cache_hit:
            return SkipDecision(skip=True, reason="head_sha unchanged: c0ffee00", head_sha=HEAD)
        return SkipDecision(skip=False, reason="cluster_cache empty for SHA")

    async def _skip_synthesis(db: Any, **kw: Any) -> SkipDecision:
        return SkipDecision(skip=synth_present, reason=None if synth_present else "no rows")

    async def _index(path: str, *, head_sha: str, max_files: int) -> object:
        world.indexed.append(head_sha)
        return SimpleNamespace(
            success=True, clusters=[], graph=nx.Graph(), file_count=3, elapsed_s=0.1, error=None
        )

    async def _persist(
        *, org_id: uuid.UUID, repo_id: uuid.UUID, head_sha: str, result: Any
    ) -> Any:
        world.persisted.append(head_sha)
        return 2, True, None, None

    monkeypatch.setattr(stage, "with_session", _session)
    monkeypatch.setattr(stage, "OrganizationRepository", _Orgs)
    monkeypatch.setattr(stage, "ensure_scan_test_worktree", _worktree)
    monkeypatch.setattr(stage, "run_git", _git)
    monkeypatch.setattr(stage, "should_skip_indexing", _skip_indexing)
    monkeypatch.setattr(stage, "should_skip_feature_synthesis", _skip_synthesis)
    monkeypatch.setattr(stage, "index_repo", _index)
    monkeypatch.setattr(stage, "persist_index_result", _persist)
    return world


def _config() -> dict[str, Any]:
    return {
        "main_branch": "main",
        "org_id": str(uuid.uuid4()),
        "scan_id": str(uuid.uuid4()),
        "repo_id": str(uuid.uuid4()),
    }


async def test_a_cache_hit_with_synthesis_present_skips_everything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _wire(monkeypatch, cache_hit=True, synth_present=True)

    out = await stage.run(CTX, [], _config())

    assert world.indexed == [] and world.persisted == []
    assert out.extras["skipped_unchanged"] is True
    assert out.extras["skipped_reason"] == "head_sha unchanged: c0ffee00"
    assert out.extras["head_sha"] == HEAD


async def test_a_cache_hit_without_synthesis_forces_the_reduction_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _wire(monkeypatch, cache_hit=True, synth_present=False)

    out = await stage.run(CTX, [], _config())

    assert world.indexed == []
    assert out.extras["skipped_unchanged"] is False
    assert "reduction chain forced" in out.extras["skipped_reason"]


async def test_a_cache_miss_runs_the_indexer_and_persists_under_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _wire(monkeypatch, cache_hit=False, synth_present=True)

    out = await stage.run(CTX, [], _config())

    assert world.indexed == [HEAD] and world.persisted == [HEAD]
    assert out.extras["skipped_unchanged"] is False
    assert out.extras["cluster_rows_written"] == 2
    assert out.extras["stats"]["files"] == 3


async def test_without_an_org_context_the_cache_is_neither_read_nor_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sandbox runs have no org: always index, never persist."""
    world = _wire(monkeypatch, cache_hit=True, synth_present=True)

    out = await stage.run(CTX, [], {"main_branch": "main", "repo_id": str(uuid.uuid4())})

    assert world.indexed == [HEAD] and world.persisted == []
    assert out.extras["cluster_rows_written"] == 0
