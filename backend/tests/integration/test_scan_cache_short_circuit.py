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

"""The SHA-keyed indexer caches and the skip checks that short-circuit a rescan.

A rescan of an unchanged ``head_sha`` must reuse ``cluster_cache`` /
``repo_graph_cache`` rows; a new SHA, another org, or ``force_reindex``
must not.
"""

from __future__ import annotations

import uuid
from typing import Any

import networkx as nx
import pytest

from app.repositories.cluster_cache import ClusterCacheRepository
from app.repositories.repo_graph_cache import RepoGraphCacheRepository
from app.services.scan.stages._skip_predicates import should_skip_indexing
from tests.integration.scan_features_bugs_support import Factory, new_org, new_repo

pytestmark = pytest.mark.integration

SHA_A = "a" * 40
SHA_B = "b" * 40


def _cluster(cid: str, symbols: int = 3) -> dict[str, Any]:
    return {
        "cluster_id": cid,
        "label": f"Cluster {cid}",
        "heuristic_label": None,
        "symbol_count": symbols,
        "cohesion": 0.5,
        "files": [f"src/{cid}.py"],
        "signature": f"sig-{cid}",
        "symbols": [f"{cid}.run"],
    }


async def _cache(factory: Factory, org: uuid.UUID, repo: uuid.UUID, sha: str, *ids: str) -> None:
    async with factory() as db:
        await ClusterCacheRepository(db, org_id=org).replace_for_repo_sha(
            repo_id=repo, head_sha=sha, rows=[_cluster(c, i + 1) for i, c in enumerate(ids)]
        )
        await db.commit()


async def _cached_ids(factory: Factory, org: uuid.UUID, repo: uuid.UUID, sha: str) -> list[str]:
    async with factory() as db:
        rows = await ClusterCacheRepository(db, org_id=org).list_for_repo_sha(
            repo_id=repo, head_sha=sha
        )
        return [r.cluster_id for r in rows]


async def _world(factory: Factory) -> tuple[uuid.UUID, uuid.UUID]:
    org = await new_org(factory)
    return org, await new_repo(factory, org)


async def test_an_unchanged_sha_skips_indexing_and_reports_the_sha(
    pg_session_factory: Factory,
) -> None:
    org, repo = await _world(pg_session_factory)
    await _cache(pg_session_factory, org, repo, SHA_A, "c0")
    async with pg_session_factory() as db:
        decision = await should_skip_indexing(db, org_id=org, repo_id=repo, head_sha=SHA_A)
    assert decision.skip is True
    assert decision.head_sha == SHA_A
    assert decision.reason == "head_sha unchanged: aaaaaaaa"


@pytest.mark.parametrize(
    ("sha", "force", "reason"),
    [
        (SHA_B, False, "cluster_cache empty for SHA"),
        (SHA_A, True, "force_reindex set"),
        ("", False, "no head_sha"),
    ],
    ids=["new-sha", "forced", "no-sha"],
)
async def test_indexing_reruns_for_a_new_sha_a_forced_run_or_no_sha(
    pg_session_factory: Factory, sha: str, force: bool, reason: str
) -> None:
    org, repo = await _world(pg_session_factory)
    await _cache(pg_session_factory, org, repo, SHA_A, "c0")
    async with pg_session_factory() as db:
        decision = await should_skip_indexing(
            db, org_id=org, repo_id=repo, head_sha=sha, force_reindex=force
        )
    assert decision.skip is False
    assert decision.reason == reason


async def test_another_orgs_cache_never_short_circuits(pg_session_factory: Factory) -> None:
    org, repo = await _world(pg_session_factory)
    stranger = await new_org(pg_session_factory)
    await _cache(pg_session_factory, org, repo, SHA_A, "c0")
    async with pg_session_factory() as db:
        decision = await should_skip_indexing(db, org_id=stranger, repo_id=repo, head_sha=SHA_A)
        rows = await ClusterCacheRepository(db, org_id=stranger).list_for_repo_sha(
            repo_id=repo, head_sha=SHA_A
        )
    assert decision.skip is False
    assert rows == []


async def test_replacing_a_sha_prunes_vanished_clusters_and_leaves_other_shas(
    pg_session_factory: Factory,
) -> None:
    org, repo = await _world(pg_session_factory)
    await _cache(pg_session_factory, org, repo, SHA_A, "c0", "c1", "c2")
    await _cache(pg_session_factory, org, repo, SHA_B, "c0", "c9")

    await _cache(pg_session_factory, org, repo, SHA_A, "c1", "c3")

    assert sorted(await _cached_ids(pg_session_factory, org, repo, SHA_A)) == ["c1", "c3"]
    assert sorted(await _cached_ids(pg_session_factory, org, repo, SHA_B)) == ["c0", "c9"]


async def test_replacing_with_nothing_empties_the_sha_so_indexing_reruns(
    pg_session_factory: Factory,
) -> None:
    org, repo = await _world(pg_session_factory)
    await _cache(pg_session_factory, org, repo, SHA_A, "c0", "c1")
    await _cache(pg_session_factory, org, repo, SHA_A)
    async with pg_session_factory() as db:
        decision = await should_skip_indexing(db, org_id=org, repo_id=repo, head_sha=SHA_A)
    assert await _cached_ids(pg_session_factory, org, repo, SHA_A) == []
    assert decision.skip is False


async def test_cached_clusters_come_back_biggest_first(pg_session_factory: Factory) -> None:
    org, repo = await _world(pg_session_factory)
    await _cache(pg_session_factory, org, repo, SHA_A, "small", "medium", "large")
    assert await _cached_ids(pg_session_factory, org, repo, SHA_A) == [
        "large",
        "medium",
        "small",
    ]


def _graph(*edges: tuple[str, str]) -> nx.Graph:
    g = nx.Graph()
    g.add_edges_from(edges)
    return g


async def test_the_call_graph_round_trips_per_sha_and_org_with_last_write_winning(
    pg_session_factory: Factory,
) -> None:
    org, repo = await _world(pg_session_factory)
    stranger = await new_org(pg_session_factory)
    async with pg_session_factory() as db:
        graphs = RepoGraphCacheRepository(db, org_id=org)
        await graphs.upsert_for_sha(repo_id=repo, head_sha=SHA_A, graph=_graph(("a", "b")))
        await graphs.upsert_for_sha(
            repo_id=repo, head_sha=SHA_A, graph=_graph(("a", "b"), ("b", "ünïcode"))
        )
        await db.commit()

    async with pg_session_factory() as db:
        hit = await RepoGraphCacheRepository(db, org_id=org).get_for_sha(
            repo_id=repo, head_sha=SHA_A
        )
        miss_sha = await RepoGraphCacheRepository(db, org_id=org).get_for_sha(
            repo_id=repo, head_sha=SHA_B
        )
        miss_org = await RepoGraphCacheRepository(db, org_id=stranger).get_for_sha(
            repo_id=repo, head_sha=SHA_A
        )

    assert hit is not None
    assert sorted(hit.nodes) == ["a", "b", "ünïcode"]
    assert hit.number_of_edges() == 2
    assert miss_sha is None and miss_org is None
