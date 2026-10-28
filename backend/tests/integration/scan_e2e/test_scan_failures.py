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

"""A rescan going wrong must fail the repo run and keep the right features.

A rescan of a changed repo soft-deletes its features up front so fresh
synthesis can reuse their titles. If synthesis then writes nothing or times
out, the run fails and the soft-deleted features have to come back. If a
later stage fails after synthesis finished, the reconciled result stands.

The preconditions use :func:`require` (``pytest.fail``) so a broken setup step
reads as such rather than as a failed restore.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.mcp import synthesis_accumulator
from app.models.scan import ScanAggregateStatus
from app.models.scan_phase import ScanPhase
from app.models.scan_run_enums import RepoRunStatus, StepStatus
from app.services.scan import stages
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript, ToolCall
from tests.fakes.git_repo import LocalGitRepo, git
from tests.fakes.seed import auth_headers
from tests.integration.scan_e2e.scan_support import (
    SYNTHESIS_MARKER,
    Factory,
    Scanned,
    active_feature_titles,
    feature_params,
    load_outcome,
    require,
    scanned_once,
    start_scan_over_http,
    synthesis_writing,
    tracked_repo,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]


async def _rescan(client: AsyncClient, s: Scanned, *, full_rescan: bool = False) -> uuid.UUID:
    return await start_scan_over_http(
        client, auth_headers(s.owner_id, s.org_id), s.repo_id, full_rescan=full_rescan
    )


async def test_agent_writing_nothing_fails_the_run_and_restores_features(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    s = await scanned_once(client, app_sessions, mcp_claude, shop_repo)
    shop_repo.commit({"shop/billing/discounts.py": "def discount(x):\n    return x\n"}, "d")
    mcp_claude.enqueue(AgentScript.ok("I could not find any features."))

    outcome = await load_outcome(app_sessions, s.org_id, await _rescan(client, s))

    require(outcome.run.status is RepoRunStatus.FAILED, "the rescan run should fail")
    require("synthesis produced 0 features" in (outcome.run.error or ""), str(outcome.run.error))
    steps = {step.phase: step.status for step in outcome.steps}
    require(steps[ScanPhase.FEATURE_SYNTHESIS] is StepStatus.FAILED, str(steps))
    require(outcome.scan.status == ScanAggregateStatus.COMPLETED.value, outcome.scan.status)
    row = await tracked_repo(app_sessions, s.org_id, s.repo_id)
    require(row.head_sha == s.head_sha, "a failed run must not advance the tracked SHA")
    assert await active_feature_titles(app_sessions, s.org_id, s.repo_id) == s.titles


async def test_timeout_discards_partial_writes_and_restores_features(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    s = await scanned_once(client, app_sessions, mcp_claude, shop_repo, timeout_seconds=1)
    half_done = ToolCall(SYNTHESIS_MARKER, lambda run: feature_params(run, 0, "Half done"))
    mcp_claude.enqueue(AgentScript.timeout(half_done))

    scan_id = await _rescan(client, s, full_rescan=True)

    outcome = await load_outcome(app_sessions, s.org_id, scan_id)
    require(outcome.run.status is RepoRunStatus.FAILED, "the timed-out run should fail")
    require("timed out" in (outcome.run.error or ""), str(outcome.run.error))
    (write,) = mcp_claude.tool_calls(SYNTHESIS_MARKER)[2:]
    require(write.status_code == 200, "the partial write reached the MCP route")
    require(mcp_claude.runs[-1].killed, "the hung agent should be killed")
    pending = synthesis_accumulator.peek_count(str(s.org_id), str(s.repo_id))
    require(pending == 0, "the partial write must not wait for the next scan")
    assert await active_feature_titles(app_sessions, s.org_id, s.repo_id) == s.titles


async def test_failure_after_synthesis_keeps_the_reconciled_features(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s = await scanned_once(client, app_sessions, mcp_claude, shop_repo)
    git(shop_repo.work, "rm", "-r", "-q", "shop/accounts")
    shop_repo.commit({}, "Drop the accounts module")
    mcp_claude.enqueue(synthesis_writing(1, prefix="Fresh"))

    async def broken_skills(*_: object) -> object:
        raise RuntimeError("skill extraction blew up")

    stages.known_stages()
    assert stages._STAGE_REGISTRY is not None
    monkeypatch.setitem(stages._STAGE_REGISTRY, "skill_extraction", broken_skills)

    outcome = await load_outcome(app_sessions, s.org_id, await _rescan(client, s))

    assert outcome.run.status is RepoRunStatus.FAILED
    assert "skill extraction blew up" in (outcome.run.error or "")
    after = await active_feature_titles(app_sessions, s.org_id, s.repo_id)
    assert len(after) == 1
    assert all(title.startswith("Feature: Fresh") for title in after)
