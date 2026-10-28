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

"""What the synthesis agent does wrong on a first scan, and how the scan copes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.mcp import synthesis_accumulator
from app.models.scan_run_enums import RepoRunStatus
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentRun, AgentScript, ToolCall
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.seed import auth_headers, seed_org, seed_repo
from tests.integration.scan_e2e.scan_support import (
    SYNTHESIS_MARKER,
    Factory,
    active_feature_titles,
    cache_counts,
    feature_params,
    load_outcome,
    start_scan_over_http,
    synthesis_writing,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]


async def test_a_write_against_another_orgs_repo_is_refused_and_kept_out(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    other = await seed_org(app_sessions)
    org = await seed_org(app_sessions)
    other_repo = await seed_repo(app_sessions, other.org_id, shop_repo)
    repo_id = await seed_repo(app_sessions, org.org_id, shop_repo)

    def into_other_org(run: AgentRun) -> dict[str, Any]:
        return feature_params(run, 0, "Smuggled") | {"repo_id": str(other_repo)}

    honest = ToolCall(SYNTHESIS_MARKER, lambda run: feature_params(run, 1, "Honest"))
    smuggled = ToolCall(SYNTHESIS_MARKER, into_other_org)
    mcp_claude.enqueue(AgentScript.ok("done", smuggled, honest))

    scan_id = await start_scan_over_http(client, auth_headers(org.owner_id, org.org_id), repo_id)

    refused, accepted = mcp_claude.tool_calls(SYNTHESIS_MARKER)
    assert refused.status_code == 200
    assert "error" in refused.response
    assert "shop-api" in str(refused.response["error"])
    assert (accepted.status_code, accepted.is_error) == (200, False)
    assert synthesis_accumulator.peek_count(str(org.org_id), str(other_repo)) == 0
    outcome = await load_outcome(app_sessions, org.org_id, scan_id)
    assert outcome.run.status is RepoRunStatus.DONE, outcome.run.error
    titles = await active_feature_titles(app_sessions, org.org_id, repo_id)
    assert len(titles) == 1
    assert next(iter(titles)).startswith("Feature: Honest")


async def test_agent_crash_fails_the_scan_and_a_retry_succeeds(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    org = await seed_org(app_sessions)
    repo_id = await seed_repo(app_sessions, org.org_id, shop_repo)
    headers = auth_headers(org.owner_id, org.org_id)
    mcp_claude.enqueue(AgentScript.crash(exit_code=1, stderr="credit balance too low"))

    failed = await load_outcome(
        app_sessions, org.org_id, await start_scan_over_http(client, headers, repo_id)
    )
    assert failed.run.status is RepoRunStatus.FAILED
    assert "credit balance too low" in (failed.run.error or "")
    assert await active_feature_titles(app_sessions, org.org_id, repo_id) == set()
    clusters, graph = await cache_counts(app_sessions, org.org_id, repo_id, shop_repo.head())
    assert (clusters >= 2, graph) == (True, True)

    mcp_claude.enqueue(synthesis_writing(2))
    retried = await load_outcome(
        app_sessions, org.org_id, await start_scan_over_http(client, headers, repo_id)
    )

    assert retried.run.status is RepoRunStatus.DONE, retried.run.error
    assert len(await active_feature_titles(app_sessions, org.org_id, repo_id)) == 2
    head = shop_repo.head()
    assert (await cache_counts(app_sessions, org.org_id, repo_id, head))[0] == clusters
