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

"""The one automatic retry when an agent's git commands were refused for auth.

The org is wired to the fake GitHub App, so the token refresh before each
spawn really mints installation tokens and re-stamps ``origin`` in the
local clones; ``fake_github.issued_tokens`` counts the mints.
"""

from __future__ import annotations

import pytest

from app.models.bud import BUDStatus
from app.models.bud_agent_task import AgentTaskStatus
from app.schemas.jobs import JobState
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.github import FakeGitHub
from tests.fakes.seed import Factory, seed_repo
from tests.integration.runner_internals.output_support import (
    TECH_SPEC,
    origin_url,
    stage_runs,
    tech_arch_output,
)
from tests.integration.runner_internals.runtime_support import JobRuntime
from tests.integration.runner_internals.stage_support import (
    activity,
    activity_types,
    add_bud,
    load_bud,
    load_task,
    seed_agent_org,
    trigger_stage,
)

pytestmark = pytest.mark.integration

AUTH_FAILURE = "fatal: Authentication failed for 'https://github.com/acme/shop-api.git/'"


async def test_auth_failure_is_retried_once_with_a_fresh_session_and_token(
    stage_claude: FakeClaudeRunner,
    fake_github: FakeGitHub,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    git_repo: LocalGitRepo,
) -> None:
    """Retry: token invalidated and re-minted, origin re-stamped, new session id."""
    org = await seed_agent_org(app_sessions, github=fake_github)
    await seed_repo(app_sessions, org.org_id, git_repo, full_name="acme/shop-api")
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.TECH_ARCH)
    stage_claude.enqueue(
        AgentScript.ok(AUTH_FAILURE), AgentScript.ok(tech_arch_output("shop-api"))
    )

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "tech_arch")
    job = await job_runtime.wait(run.job_id)

    assert job.state == JobState.COMPLETED
    first, second = stage_runs(stage_claude)
    assert first.prompt == second.prompt
    assert first.flag("--session-id") != second.flag("--session-id")
    assert second.flag("--resume") is None
    assert fake_github.issued_tokens == ["ghs_fake0001", "ghs_fake0002"]
    assert "x-access-token:ghs_fake0002@github.com/acme/shop-api" in origin_url(git_repo)
    assert (await load_bud(app_sessions, org.org_id, bud.id)).tech_spec_md == TECH_SPEC
    kinds = activity_types(await activity(app_sessions, org.org_id, bud.id))
    # skill_invoked commits first; agent_retried and skill_completed share one
    # transaction (and so one created_at), so only their set is fixed.
    assert kinds[0] == "skill_invoked"
    assert sorted(kinds[1:]) == ["agent_retried", "skill_completed"]


async def test_second_auth_failure_is_not_retried_again(
    stage_claude: FakeClaudeRunner,
    fake_github: FakeGitHub,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    git_repo: LocalGitRepo,
) -> None:
    """Exactly one retry: the second refusal is what the result handler gets."""
    org = await seed_agent_org(app_sessions, github=fake_github)
    await seed_repo(app_sessions, org.org_id, git_repo, full_name="acme/shop-api")
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.TECH_ARCH)
    stage_claude.default = AgentScript.ok(AUTH_FAILURE)

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "tech_arch")
    await job_runtime.wait(run.job_id)

    assert len(stage_runs(stage_claude)) == 2
    rows = await activity(app_sessions, org.org_id, bud.id)
    assert activity_types(rows).count("agent_retried") == 1


@pytest.mark.xfail(
    strict=True,
    reason=(
        "after a second git auth refusal the git error text is saved as the tech spec "
        "and the task completes. Not fixed here: the auth-failure pattern also matches "
        "ordinary prose about authentication, so failing such runs needs a product call"
    ),
)
async def test_second_auth_failure_fails_the_task_instead_of_saving_the_error(
    stage_claude: FakeClaudeRunner,
    fake_github: FakeGitHub,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    git_repo: LocalGitRepo,
) -> None:
    """Two refusals in a row: the spec the BUD has stays and the task fails."""
    org = await seed_agent_org(app_sessions, github=fake_github)
    await seed_repo(app_sessions, org.org_id, git_repo, full_name="acme/shop-api")
    bud = await add_bud(
        app_sessions, org.org_id, status=BUDStatus.TECH_ARCH, tech_spec_md="# Old plan"
    )
    stage_claude.default = AgentScript.ok(AUTH_FAILURE)

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "tech_arch")
    await job_runtime.wait(run.job_id)

    assert (await load_bud(app_sessions, org.org_id, bud.id)).tech_spec_md == "# Old plan"
    assert (await load_task(app_sessions, run.task_id)).status == AgentTaskStatus.FAILED


async def test_crash_with_auth_text_is_not_retried(
    stage_claude: FakeClaudeRunner,
    fake_github: FakeGitHub,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    git_repo: LocalGitRepo,
) -> None:
    """A failed run is reported as failed, not masked as flaky auth."""
    org = await seed_agent_org(app_sessions, github=fake_github)
    await seed_repo(app_sessions, org.org_id, git_repo, full_name="acme/shop-api")
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.TECH_ARCH)
    stage_claude.enqueue(AgentScript.crash(stderr=AUTH_FAILURE))

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "tech_arch")
    job = await job_runtime.wait(run.job_id)

    assert job.state == JobState.FAILED
    assert len(stage_runs(stage_claude)) == 1
    assert fake_github.issued_tokens == ["ghs_fake0001"]
    assert (await load_task(app_sessions, run.task_id)).status == AgentTaskStatus.FAILED
