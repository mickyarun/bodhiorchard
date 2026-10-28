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

"""Which runs the git auth retry covers: no-repo stages are skipped, every repo is re-stamped."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.models.bud import BUDStatus
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.github import FakeGitHub
from tests.fakes.seed import Factory, seed_repo
from tests.integration.runner_internals.output_support import (
    origin_url,
    stage_runs,
)
from tests.integration.runner_internals.runtime_support import JobRuntime
from tests.integration.runner_internals.stage_support import (
    add_bud,
    load_bud,
    seed_agent_org,
    trigger_stage,
)

pytestmark = pytest.mark.integration


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
    assert "ghs_fake0002@github.com/acme/shop-api" in origin_url(git_repo)
    assert "ghs_fake0002@github.com/acme/billing-api" in origin_url(billing)
    assert stage_runs(stage_claude)[0].cwd == git_repo.path
