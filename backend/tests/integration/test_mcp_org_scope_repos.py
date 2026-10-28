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

"""The six ``code_*`` graph tools stay inside the token's org.

An id from another org must read as unknown, and the "known repos" hint an
agent gets back must list only the caller's own repositories.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.mcp_seed import (
    add_repo,
    make_tenant,
)
from tests.integration.mcp_support import (
    Factory,
    call,
    mcp_env,  # noqa: F401
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("mcp_env")]

_CODE_TOOLS: dict[str, dict[str, object]] = {
    "code_impact": {"target": "createTask"},
    "code_query": {"query": "task"},
    "code_context": {"symbol": "createTask"},
    "code_community": {"cluster_id": "c0"},
    "code_god_nodes": {},
    "code_stats": {},
}


@pytest.mark.parametrize("tool", sorted(_CODE_TOOLS))
async def test_code_tools_refuse_other_org_repo(
    client: AsyncClient, pg_session_factory: Factory, tool: str
) -> None:
    """B's repo id is "not tracked here", and only A's repos are suggested."""
    org_a = await make_tenant(pg_session_factory)
    org_b = await make_tenant(pg_session_factory)
    a_repo = await add_repo(pg_session_factory, org_a.org_id, "a-api")
    b_repo = await add_repo(pg_session_factory, org_b.org_id, "b-secret-repo")

    response = await call(client, org_a.token, tool, {**_CODE_TOOLS[tool], "repo_id": str(b_repo)})

    assert response.status_code == 200
    error = response.json()["error"]
    assert f"repo_id {b_repo} is not a tracked repository in this organization" in error
    assert f"a-api={a_repo}" in error
    assert "b-secret-repo" not in error


@pytest.mark.parametrize("tool", sorted(_CODE_TOOLS))
async def test_code_tools_need_a_repo_id(
    client: AsyncClient, pg_session_factory: Factory, tool: str
) -> None:
    """Omitting repo_id is an error envelope, not a crash."""
    tenant = await make_tenant(pg_session_factory)
    response = await call(client, tenant.token, tool, dict(_CODE_TOOLS[tool]))
    assert response.status_code == 200
    assert "repo_id" in response.json()["error"]


async def test_code_tool_with_repo_name_lists_own_repos(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A repo name (a common agent mistake) gets the id list back."""
    tenant = await make_tenant(pg_session_factory)
    repo_id = await add_repo(pg_session_factory, tenant.org_id, "taskflow-api")

    response = await call(client, tenant.token, "code_stats", {"repo_id": "taskflow-api"})

    error = response.json()["error"]
    assert error.startswith("repo_id must be a tracked repository UUID, got 'taskflow-api'")
    assert f"taskflow-api={repo_id}" in error


async def test_code_tool_on_unscanned_own_repo_says_not_scanned(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A valid id for a repo that was never scanned reports exactly that."""
    tenant = await make_tenant(pg_session_factory)
    repo_id = await add_repo(pg_session_factory, tenant.org_id, "fresh")

    response = await call(client, tenant.token, "code_stats", {"repo_id": str(repo_id)})

    assert "has not been scanned yet" in response.json()["error"]
