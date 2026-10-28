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

"""``code_*`` tools tell a bad repo_id apart from a repo with no graph.

An agent that passed a repo name got "no cached graph for this repo" five
times and concluded the repo was unindexed. A wrong id must instead come back
with the org's repos and their ids so the agent can retry correctly.
"""

import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import networkx as nx
import pytest

from app.mcp.handlers_code_graph import handle_code_community, handle_code_stats

API_ID = uuid.uuid4()
TRIPLES = [(API_ID, "/repos/taskflow-api", "taskflow-api")]


@pytest.fixture
def tracked() -> Iterator[MagicMock]:
    repo = MagicMock(
        get_active_id_path_name=AsyncMock(return_value=TRIPLES),
        get_by_id=AsyncMock(return_value=None),
    )
    with patch("app.mcp.code_graph_repo.TrackedRepoRepository", return_value=repo):
        yield repo


def _org() -> Any:
    return MagicMock(id=uuid.uuid4())


@pytest.mark.asyncio
async def test_repo_name_instead_of_uuid_lists_known_repos(tracked: MagicMock) -> None:
    result = await handle_code_stats(MagicMock(), _org(), {"repo_id": "taskflow-api"})
    error = result["error"]
    assert "repo_id must be a tracked repository UUID" in error
    assert "'taskflow-api'" in error
    assert f"taskflow-api={API_ID}" in error


@pytest.mark.asyncio
async def test_unknown_uuid_is_reported_as_not_tracked(tracked: MagicMock) -> None:
    stray = uuid.uuid4()
    result = await handle_code_stats(MagicMock(), _org(), {"repo_id": str(stray)})
    error = result["error"]
    assert f"repo_id {stray} is not a tracked repository in this organization" in error
    assert f"taskflow-api={API_ID}" in error


@pytest.mark.asyncio
async def test_known_repo_without_graph_says_so(tracked: MagicMock) -> None:
    tracked.get_by_id.return_value = MagicMock(head_sha="abc123")
    tracked.get_by_id.return_value.name = "taskflow-api"
    with patch(
        "app.mcp.handlers_code_graph.RepoGraphCacheRepository",
        return_value=MagicMock(get_for_sha=AsyncMock(return_value=None)),
    ):
        result = await handle_code_stats(MagicMock(), _org(), {"repo_id": str(API_ID)})
    error = result["error"]
    assert "no cached code graph for repo 'taskflow-api'" in error
    assert "abc123" in error
    assert "Known repos" not in error


@pytest.mark.asyncio
async def test_never_scanned_repo_says_so(tracked: MagicMock) -> None:
    tracked.get_by_id.return_value = MagicMock(head_sha=None)
    tracked.get_by_id.return_value.name = "taskflow-api"
    with patch(
        "app.mcp.code_graph_repo.ClusterCacheRepository",
        return_value=MagicMock(latest_head_sha=AsyncMock(return_value=None)),
    ):
        result = await handle_code_community(
            MagicMock(), _org(), {"repo_id": str(API_ID), "cluster_id": "c0"}
        )
    assert "has not been scanned yet" in result["error"]


@pytest.mark.asyncio
async def test_valid_repo_returns_stats(tracked: MagicMock) -> None:
    tracked.get_by_id.return_value = MagicMock(head_sha="abc123")
    tracked.get_by_id.return_value.name = "taskflow-api"
    graph = nx.DiGraph()
    graph.add_node("a", source_file="src/a.ts")
    graph.add_node("b", source_file="src/b.ts")
    graph.add_edge("a", "b")
    with patch(
        "app.mcp.handlers_code_graph.RepoGraphCacheRepository",
        return_value=MagicMock(get_for_sha=AsyncMock(return_value=graph)),
    ):
        result = await handle_code_stats(MagicMock(), _org(), {"repo_id": str(API_ID)})
    assert result["head_sha"] == "abc123"
    assert result["node_count"] == 2
    assert result["file_extensions"] == {"ts": 2}
