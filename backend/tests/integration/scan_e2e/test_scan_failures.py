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

"""Synthesis going wrong mid-scan must fail the repo run and keep the old features.

A rescan soft-deletes the repo's features up front so fresh synthesis can
reuse their titles. When the agent then writes nothing, times out or crashes,
the run has to fail and the soft-deleted features have to come back.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.models.scan_phase import ScanPhase
from app.models.scan_run_enums import RepoRunStatus, StepStatus
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript, ToolCall
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.seed import SeededOrg, auth_headers, seed_org, seed_repo
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

# The workflow marks a failing run FAILED without raising, and the fanout only
# restored the soft-deleted slice on an exception. Remove once the fix lands.
FEATURES_NOT_RESTORED = pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="failed repo run leaves its features soft-deleted; "
    "fixed by branch fix/scan-failed-run-restores-features",
)


async def _scanned_once(
    client: AsyncClient, factory: Factory, claude: FakeClaudeRunner, repo: LocalGitRepo
) -> tuple[SeededOrg, uuid.UUID, set[str]]:
    org = await seed_org(factory, config={"scan": {"timeout_seconds": 1}})
    repo_id = await seed_repo(factory, org.org_id, repo)
    claude.enqueue(synthesis_writing(2))
    await start_scan_over_http(client, auth_headers(org.owner_id, org.org_id), repo_id)
    titles = await active_feature_titles(factory, org.org_id, repo_id)
    assert len(titles) == 2
    return org, repo_id, titles


@FEATURES_NOT_RESTORED
async def test_agent_writing_nothing_fails_the_run_and_restores_features(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    org, repo_id, before = await _scanned_once(client, app_sessions, mcp_claude, shop_repo)
    shop_repo.commit({"shop/billing/discounts.py": "def discount(x):\n    return x\n"}, "d")
    mcp_claude.enqueue(AgentScript.ok("I could not find any features."))

    scan_id = await start_scan_over_http(client, auth_headers(org.owner_id, org.org_id), repo_id)

    outcome = await load_outcome(app_sessions, org.org_id, scan_id)
    assert outcome.run.status is RepoRunStatus.FAILED
    assert "synthesis produced 0 features" in (outcome.run.error or "")
    by_phase = {step.phase: step.status for step in outcome.steps}
    assert by_phase[ScanPhase.FEATURE_SYNTHESIS] is StepStatus.FAILED
    assert len(mcp_claude.runs) == 2
    assert await active_feature_titles(app_sessions, org.org_id, repo_id) == before


@FEATURES_NOT_RESTORED
async def test_timeout_discards_partial_writes_and_restores_features(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    org, repo_id, before = await _scanned_once(client, app_sessions, mcp_claude, shop_repo)
    half_done = ToolCall(SYNTHESIS_MARKER, lambda run: feature_params(run, 0, "Half done"))
    mcp_claude.enqueue(AgentScript.timeout(half_done))

    scan_id = await start_scan_over_http(
        client, auth_headers(org.owner_id, org.org_id), repo_id, full_rescan=True
    )

    outcome = await load_outcome(app_sessions, org.org_id, scan_id)
    assert outcome.run.status is RepoRunStatus.FAILED
    assert "timed out" in (outcome.run.error or "")
    (write,) = mcp_claude.tool_calls(SYNTHESIS_MARKER)[2:]
    assert write.status_code == 200
    assert mcp_claude.runs[-1].killed is True
    after = await active_feature_titles(app_sessions, org.org_id, repo_id)
    assert after == before
    assert not any(title.startswith("Feature: Half done") for title in after)


async def test_writes_for_another_orgs_repo_are_refused_and_fail_the_run(
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

    def into_other_org(run: object) -> dict[str, object]:
        return {
            "name": "Smuggled",
            "description": "Written against a repo this org does not own.",
            "source_community_ids": ["c0"],
            "repo_name": "shop-api",
            "repo_id": str(other_repo),
        }

    mcp_claude.enqueue(AgentScript.ok("done", ToolCall(SYNTHESIS_MARKER, into_other_org)))

    scan_id = await start_scan_over_http(client, auth_headers(org.owner_id, org.org_id), repo_id)

    outcome = await load_outcome(app_sessions, org.org_id, scan_id)
    (write,) = mcp_claude.tool_calls(SYNTHESIS_MARKER)
    assert write.is_error is True
    assert outcome.run.status is RepoRunStatus.FAILED
    assert await active_feature_titles(app_sessions, org.org_id, repo_id) == set()
    assert await active_feature_titles(app_sessions, other.org_id, other_repo) == set()


async def test_agent_crash_on_first_scan_keeps_the_index_for_the_retry(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    org = await seed_org(app_sessions)
    repo_id = await seed_repo(app_sessions, org.org_id, shop_repo)
    mcp_claude.enqueue(AgentScript.crash(exit_code=1, stderr="credit balance too low"))

    scan_id = await start_scan_over_http(client, auth_headers(org.owner_id, org.org_id), repo_id)

    outcome = await load_outcome(app_sessions, org.org_id, scan_id)
    assert outcome.run.status is RepoRunStatus.FAILED
    assert "credit balance too low" in (outcome.run.error or "")
    assert await active_feature_titles(app_sessions, org.org_id, repo_id) == set()
    clusters, graph = await cache_counts(app_sessions, org.org_id, repo_id, shop_repo.head("main"))
    assert clusters >= 2
    assert graph is True
