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

"""The database-bound fakes: scripted MCP calls and background sessions on Postgres."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select

from app.mcp import audit
from app.mcp.auth import create_internal_mcp_token
from app.models.mcp_audit_log import MCPAuditLogEntry
from app.repositories.organization import OrganizationRepository
from app.services.claude_runner import ClaudeRunnerConfig, MCPServerConfig, run_claude_code
from app.services.github_install_repos import list_installation_repos
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript, ToolCall
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.github import FakeGitHub
from tests.fakes.seed import Factory, seed_org, seed_repo

pytestmark = pytest.mark.integration


async def test_scripted_tool_calls_run_through_the_real_mcp_route_and_audit(
    mcp_claude: FakeClaudeRunner, app_sessions: Factory, tmp_path: Path
) -> None:
    org = await seed_org(app_sessions)
    token = create_internal_mcp_token(org.org_id)
    mcp_claude.enqueue(
        AgentScript.ok(
            "ok", ToolCall("get_features", {"query": "orders"}), ToolCall("no_such_tool", {})
        )
    )
    config = ClaudeRunnerConfig(mcp=MCPServerConfig("http://backend", token))

    result = await run_claude_code("list features", tmp_path, config)
    await asyncio.gather(*audit._audit_tasks)

    assert result.success is True
    features, unknown = mcp_claude.tool_calls()
    assert (features.status_code, features.is_error) == (200, False)
    assert (unknown.status_code, unknown.is_error) == (404, True)
    async with app_sessions() as db:
        rows = (
            await db.scalars(select(MCPAuditLogEntry).where(MCPAuditLogEntry.org_id == org.org_id))
        ).all()
    assert sorted((r.tool_name, r.status_code) for r in rows) == [
        ("get_features", 200),
        ("no_such_tool", 404),
    ]


async def test_a_bad_token_is_refused_by_the_real_auth(
    mcp_claude: FakeClaudeRunner, app_sessions: Factory, tmp_path: Path
) -> None:
    mcp_claude.enqueue(AgentScript.ok("ok", ToolCall("get_features", {})))
    config = ClaudeRunnerConfig(mcp=MCPServerConfig("http://backend", "not-a-token"))

    await run_claude_code("p", tmp_path, config)

    (call,) = mcp_claude.tool_calls()
    assert call.status_code == 401


async def test_installable_repos_page_through_the_fake_and_mark_tracked(
    fake_github: FakeGitHub, app_sessions: Factory, git_repo: LocalGitRepo
) -> None:
    for name in ("shop-api", "billing", "web"):
        fake_github.add_repo(f"acme/{name}")
    org = await seed_org(app_sessions, github=fake_github)
    await seed_repo(app_sessions, org.org_id, git_repo, full_name="acme/shop-api")

    async with app_sessions() as db:
        org_row = await OrganizationRepository(db).get_by_id(org.org_id)
        assert org_row is not None
        repos = await list_installation_repos(org_row, db)

    assert [(r.full_name, r.already_tracked) for r in repos] == [
        ("acme/shop-api", True),
        ("acme/billing", False),
        ("acme/web", False),
    ]
    assert len([r for r in fake_github.requests if "repositories" in r.url.path]) == 2
