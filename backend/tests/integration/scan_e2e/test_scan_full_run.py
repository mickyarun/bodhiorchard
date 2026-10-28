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

"""A full first scan of a real git repo, from the HTTP request to the features.

Nothing below the HTTP route is mocked except the agent CLI: the worktree is
refreshed from a local ``origin``, the real indexer clusters the code, every
reduction stage runs, the scripted synthesis agent files features through
the real MCP route, and the global phases finish the scan.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from app.models.scan import ScanAggregateStatus
from app.models.scan_phase import ScanPhase
from app.models.scan_run_enums import RepoRunStatus, StepStatus
from tests.fakes.app_state import EventRecorder
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.git_repo import LocalGitRepo, git
from tests.fakes.seed import auth_headers, seed_org, seed_repo
from tests.integration.scan_e2e.scan_support import (
    SYNTHESIS_MARKER,
    Factory,
    active_feature_titles,
    cache_counts,
    load_outcome,
    prompt_clusters,
    start_scan_over_http,
    synthesis_writing,
    tracked_repo,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]


async def test_first_scan_indexes_synthesises_and_completes(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
    data_dir: Path,
    event_recorder: EventRecorder,
) -> None:
    org = await seed_org(app_sessions)
    repo_id = await seed_repo(app_sessions, org.org_id, shop_repo)
    mcp_claude.when(SYNTHESIS_MARKER, synthesis_writing(2))

    scan_id = await start_scan_over_http(client, auth_headers(org.owner_id, org.org_id), repo_id)

    outcome = await load_outcome(app_sessions, org.org_id, scan_id)
    assert outcome.scan.status == ScanAggregateStatus.COMPLETED.value
    assert outcome.run.status is RepoRunStatus.DONE, outcome.run.error
    head = shop_repo.head("main")
    clusters, graph = await cache_counts(app_sessions, org.org_id, repo_id, head)
    assert clusters >= 2
    assert graph is True
    (agent_run,) = mcp_claude.runs
    assert len(prompt_clusters(agent_run.prompt)) >= 2
    assert str(repo_id) in agent_run.prompt
    writes = mcp_claude.tool_calls(SYNTHESIS_MARKER)
    assert [(w.status_code, w.is_error) for w in writes] == [(200, False), (200, False)]
    titles = await active_feature_titles(app_sessions, org.org_id, repo_id)
    assert titles == {f"Feature: {w.params['name']}" for w in writes}
    by_phase = {step.phase: step.status for step in outcome.steps}
    assert by_phase[ScanPhase.CODE_INDEX] is StepStatus.DONE
    assert by_phase[ScanPhase.FEATURE_SYNTHESIS] is StepStatus.DONE
    assert StepStatus.FAILED not in by_phase.values()
    row = await tracked_repo(app_sessions, org.org_id, repo_id)
    assert row.head_sha == head
    assert row.setup_branch_pushed_at is not None
    origin_branches = git(shop_repo.origin, "branch", "--format=%(refname:short)").split()
    assert any(name.startswith("bodhiorchard/") for name in origin_branches)
    await event_recorder.settle()
    tool_events = event_recorder.payloads(f"scan_synthesis_tool:{scan_id}")
    assert [e["tool"] for e in tool_events] == [f"mcp__bodhiorchard__{SYNTHESIS_MARKER}"] * 2


async def test_clone_on_another_branch_is_scanned_through_a_sandbox_worktree(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    refunds = {"shop/orders/refunds.py": "def refund_order(order):\n    return order\n"}
    newer = shop_repo.commit(refunds, "Add refunds")
    git(shop_repo.work, "checkout", "-q", "develop")
    org = await seed_org(app_sessions)
    repo_id = await seed_repo(app_sessions, org.org_id, shop_repo)
    mcp_claude.when(SYNTHESIS_MARKER, synthesis_writing(1))

    scan_id = await start_scan_over_http(client, auth_headers(org.owner_id, org.org_id), repo_id)

    outcome = await load_outcome(app_sessions, org.org_id, scan_id)
    assert outcome.run.status is RepoRunStatus.DONE, outcome.run.error
    worktree = data_dir / "scan-worktrees" / shop_repo.name / "main"
    assert git(worktree, "rev-parse", "HEAD") == newer
    assert git(shop_repo.work, "rev-parse", "--abbrev-ref", "HEAD") == "develop"
    (agent_run,) = mcp_claude.runs
    files = [f for c in prompt_clusters(agent_run.prompt) for f in c["files"]]
    assert any(f.endswith("refunds.py") for f in files)


async def test_rescan_at_the_same_sha_reuses_the_caches_and_skips_the_agent(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    org = await seed_org(app_sessions)
    repo_id = await seed_repo(app_sessions, org.org_id, shop_repo)
    headers = auth_headers(org.owner_id, org.org_id)
    mcp_claude.when(SYNTHESIS_MARKER, synthesis_writing(2))
    await start_scan_over_http(client, headers, repo_id)
    before = await active_feature_titles(app_sessions, org.org_id, repo_id)

    second = await start_scan_over_http(client, headers, repo_id)

    outcome = await load_outcome(app_sessions, org.org_id, second)
    assert outcome.run.status in {RepoRunStatus.DONE, RepoRunStatus.SKIPPED_UNCHANGED}
    by_phase = {step.phase: step.status for step in outcome.steps}
    assert by_phase[ScanPhase.FEATURE_SYNTHESIS] is StepStatus.SKIPPED_CACHE
    assert len(mcp_claude.runs) == 1
    assert await active_feature_titles(app_sessions, org.org_id, repo_id) == before
