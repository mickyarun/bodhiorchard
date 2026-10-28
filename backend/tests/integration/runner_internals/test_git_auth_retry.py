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

from collections.abc import Callable

import pytest

from app.models.bud import BUDStatus
from app.models.bud_agent_task import AgentTaskStatus
from app.schemas.jobs import JobState
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript
from tests.fakes.git_repo import LocalGitRepo, git
from tests.fakes.github import FakeGitHub
from tests.fakes.seed import Factory, seed_repo
from tests.integration.runner_internals.output_support import (
    TECH_SPEC,
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


def _origin(repo: LocalGitRepo) -> str:
    return git(repo.work, "remote", "get-url", "origin")


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
    assert "x-access-token:ghs_fake0002@github.com/acme/shop-api" in _origin(git_repo)
    assert (await load_bud(app_sessions, org.org_id, bud.id)).tech_spec_md == TECH_SPEC
    rows = await activity(app_sessions, org.org_id, bud.id)
    assert sorted(activity_types(rows)) == ["agent_retried", "skill_completed", "skill_invoked"]


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
    assert (await load_bud(app_sessions, org.org_id, bud.id)).tech_spec_md == AUTH_FAILURE


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


async def test_stage_without_a_repo_is_not_retried_for_auth_wording(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """The requirements agent runs with no repo; auth-looking prose is just prose."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, requirements_md=None)
    stage_claude.enqueue(AgentScript.ok("## Risks\n\nBad credentials on the partner API."))

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "bud")
    await job_runtime.wait(run.job_id)

    assert len(stage_runs(stage_claude)) == 1
    stored = await load_bud(app_sessions, org.org_id, bud.id)
    assert stored.requirements_md == "## Risks\n\nBad credentials on the partner API."


async def test_retry_restamps_every_confirmed_repo(
    stage_claude: FakeClaudeRunner,
    fake_github: FakeGitHub,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    git_repo: LocalGitRepo,
    git_repo_factory: Callable[..., LocalGitRepo],
) -> None:
    """A multi-repo testing run refreshes ``origin`` in each confirmed clone."""
    billing = git_repo_factory("billing-api")
    org = await seed_agent_org(app_sessions, github=fake_github)
    await seed_repo(app_sessions, org.org_id, git_repo, full_name="acme/shop-api")
    await seed_repo(app_sessions, org.org_id, billing, full_name="acme/billing-api")
    confirmed = [{"repo_path": r.path, "repo_name": r.name} for r in (git_repo, billing)]
    bud = await add_bud(
        app_sessions,
        org.org_id,
        status=BUDStatus.TESTING,
        metadata_={"confirmed_repos": confirmed},
    )
    stage_claude.enqueue(
        AgentScript.ok("remote: Repository not found."),
        AgentScript.ok('{"automation_test_cases": [], "manual_test_cases": [{"id": "TC-1"}]}'),
    )

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "testing")
    await job_runtime.wait(run.job_id)

    assert len(stage_runs(stage_claude)) == 2
    assert "ghs_fake0002@github.com/acme/shop-api" in _origin(git_repo)
    assert "ghs_fake0002@github.com/acme/billing-api" in _origin(billing)
    assert stage_runs(stage_claude)[0].cwd == git_repo.path
