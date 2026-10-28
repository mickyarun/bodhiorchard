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

"""Repo-keyed MCP tools stay inside the token's org.

Covers the six ``code_*`` graph tools, the design-system tools, BUD
design reads and team context. An id from another org must read as
unknown, and the "known repos" hint an agent gets back must list only the
caller's own repositories.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.models.bud import BUDDesign, BUDDesignStatus
from app.models.design_system import DesignSystemRef
from app.models.feature import Feature
from app.models.skill_profile import SkillProfile
from tests.integration.mcp_support import (
    Factory,
    add_bud,
    add_repo,
    call,
    isolate_side_channels,
    make_tenant,
)

pytestmark = pytest.mark.integration

_CODE_TOOLS: dict[str, dict[str, object]] = {
    "code_impact": {"target": "createTask"},
    "code_query": {"query": "task"},
    "code_context": {"symbol": "createTask"},
    "code_community": {"cluster_id": "c0"},
    "code_god_nodes": {},
    "code_stats": {},
}


@pytest.fixture(autouse=True)
def _side_channels(monkeypatch: pytest.MonkeyPatch, pg_session_factory: Factory) -> None:
    isolate_side_channels(monkeypatch, pg_session_factory)


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


async def _add_design_system(factory: Factory, org_id: uuid.UUID, repo_id: uuid.UUID) -> None:
    async with factory() as db:
        db.add(
            DesignSystemRef(
                org_id=org_id,
                repo_id=repo_id,
                is_default=True,
                content="B brand tokens",
                extracted_at=datetime.now(UTC),
            )
        )
        await db.commit()


async def test_design_system_tools_hide_other_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """B's design system is neither listed nor readable with A's token."""
    org_a = await make_tenant(pg_session_factory)
    org_b = await make_tenant(pg_session_factory)
    b_repo = await add_repo(pg_session_factory, org_b.org_id, "b-web")
    await _add_design_system(pg_session_factory, org_b.org_id, b_repo)

    listed = await call(client, org_a.token, "list_design_systems")
    by_repo = await call(client, org_a.token, "get_design_system", {"repo_id": str(b_repo)})
    default = await call(client, org_a.token, "get_design_system")
    own = await call(client, org_b.token, "get_design_system", {"repo_id": str(b_repo)})

    assert listed.json() == {"design_systems": [], "count": 0}
    assert by_repo.json()["found"] is False
    assert default.json()["found"] is False
    assert own.json()["content"] == "B brand tokens"


async def test_bud_designs_of_other_org_are_not_returned(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Reading designs by B's BUD id with A's token finds nothing."""
    org_a = await make_tenant(pg_session_factory)
    org_b = await make_tenant(pg_session_factory)
    b_bud = await add_bud(pg_session_factory, org_b.org_id, 1)
    async with pg_session_factory() as db:
        db.add(
            BUDDesign(
                org_id=org_b.org_id,
                bud_id=b_bud,
                design_html="<p>B wireframe</p>",
                status=BUDDesignStatus.READY,
            )
        )
        await db.commit()

    theirs = await call(
        client, org_a.token, "get_bud_designs", {"bud_id": str(b_bud), "include_non_ready": True}
    )
    mine = await call(client, org_b.token, "get_bud_designs", {"bud_id": str(b_bud)})

    assert theirs.json()["designs"] == []
    assert [d["design_html"] for d in mine.json()["designs"]] == ["<p>B wireframe</p>"]


@pytest.mark.parametrize("tool", ["get_bud_designs", "write_bud_design"])
@pytest.mark.parametrize("bad", [{"bud_id": "BUD-001"}, {"bud_id": "   "}])
async def test_design_tools_reject_malformed_bud_id(
    client: AsyncClient, pg_session_factory: Factory, tool: str, bad: dict[str, object]
) -> None:
    """A BUD number or a blank where a UUID belongs is a clean error."""
    tenant = await make_tenant(pg_session_factory)
    response = await call(client, tenant.token, tool, {**bad, "html": "<p>x</p>"})
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "bud_id" in response.json()["error"]


async def test_team_context_lists_only_own_members(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Skill profiles from B never appear in A's team context."""
    org_a = await make_tenant(pg_session_factory)
    org_b = await make_tenant(pg_session_factory)
    async with pg_session_factory() as db:
        for tenant, module in ((org_a, "billing"), (org_b, "secret-module")):
            feature = Feature(
                org_id=tenant.org_id,
                feature_title=module,
                description=module,
                cluster_signature=uuid.uuid4().hex,
            )
            db.add(feature)
            await db.flush()
            db.add(
                SkillProfile(
                    org_id=tenant.org_id,
                    user_id=tenant.user_id,
                    module=module,
                    feature_id=feature.id,
                    skill_score=0.5,
                )
            )
        await db.commit()

    response = await call(client, org_a.token, "get_team_context")

    team = response.json()["team"]
    assert [m["name"] for member in team for m in member["modules"]] == ["billing"]
