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

"""AI settings saved over HTTP, then a real agent job: what the CLI receives, what is logged."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from httpx import AsyncClient

from app.models.bud import BUDStatus
from app.repositories.organization import OrganizationRepository
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript
from tests.fakes.seed import Factory, SeededOrg, auth_headers
from tests.integration.runner_internals.output_support import stage_runs
from tests.integration.runner_internals.runtime_support import JobRuntime
from tests.integration.runner_internals.stage_support import add_bud, seed_agent_org, trigger_stage
from tests.services.runner_internals.log_tap import LogTap, everything_logged

pytestmark = pytest.mark.integration

API_KEY = "sk-ant-api03-jobs-env-secret"
OAUTH = "sk-ant-oat01-jobs-env-token"


async def _save(client: AsyncClient, org: SeededOrg, **body: Any) -> None:
    """PATCH the org's AI settings as its owner."""
    response = await client.patch(
        "/api/v1/settings/claude",
        json={"provider": "claude", **body},
        headers=auth_headers(org.owner_id, org.org_id),
    )
    assert response.status_code == 200, response.text


async def _agent_env(
    factory: Factory, runtime: JobRuntime, fake: FakeClaudeRunner, org: SeededOrg
) -> dict[str, str]:
    """Run one learning-stage job and return the env its CLI was spawned with."""
    bud = await add_bud(factory, org.org_id, status=BUDStatus.CLOSED)
    fake.enqueue(AgentScript.ok("# Recap"))
    run = await trigger_stage(factory, org.org_id, bud.id, "closed")
    await runtime.wait(run.job_id)
    return stage_runs(fake)[-1].env


async def test_api_key_saved_in_settings_reaches_the_job_but_no_log_or_column(
    stage_claude: FakeClaudeRunner,
    client: AsyncClient,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    cred_tap: LogTap,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The key is stored encrypted, handed to the CLI, and in no captured log output."""
    caplog.set_level(logging.DEBUG)
    org = await seed_agent_org(app_sessions)

    await _save(client, org, auth_mode="api_key", api_key=API_KEY)
    env = await _agent_env(app_sessions, job_runtime, stage_claude, org)

    assert env["ANTHROPIC_API_KEY"] == API_KEY
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    async with app_sessions() as db:
        stored = await OrganizationRepository(db).get_by_id(org.org_id)
    assert stored is not None and stored.claude_api_key_encrypted is not None
    assert stored.claude_api_key_encrypted.startswith("enc:")
    assert API_KEY not in stored.claude_api_key_encrypted
    events = set(cred_tap.events())
    assert {"ai_settings_updated", "ai_env_credential_applied", "claude_run_start"} <= events
    assert {"bud_agent_phase", "job_created"} <= events
    logged = everything_logged(cred_tap, caplog, capsys)
    # A module outside the tap (the learning result handler) is captured too.
    assert "learning_result_metrics_missing" in logged
    assert API_KEY not in logged


async def test_switching_to_subscription_hands_the_next_job_only_the_token(
    stage_claude: FakeClaudeRunner,
    client: AsyncClient,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    cred_tap: LogTap,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """api_key → subscription over HTTP: the Anthropic key is cleared before the next run."""
    caplog.set_level(logging.DEBUG)
    org = await seed_agent_org(app_sessions)
    await _save(client, org, auth_mode="api_key", api_key=API_KEY)
    first = await _agent_env(app_sessions, job_runtime, stage_claude, org)

    await _save(client, org, auth_mode="subscription", oauth_token=OAUTH)
    second = await _agent_env(app_sessions, job_runtime, stage_claude, org)

    assert first.get("ANTHROPIC_API_KEY") == API_KEY
    assert (second.get("ANTHROPIC_API_KEY"), second.get("CLAUDE_CODE_OAUTH_TOKEN")) == (
        None,
        OAUTH,
    )
    logged = everything_logged(cred_tap, caplog, capsys)
    assert API_KEY not in logged and OAUTH not in logged


@pytest.mark.xfail(
    strict=True,
    reason=(
        "host mode keeps an ANTHROPIC_API_KEY the app itself injected, so switching "
        "api_key → host still runs on the old key; fixed by branch "
        "fix/host-mode-drops-injected-key"
    ),
)
@pytest.mark.usefixtures("cred_tap")
async def test_switching_back_to_host_stops_using_the_saved_key(
    stage_claude: FakeClaudeRunner,
    client: AsyncClient,
    app_sessions: Factory,
    job_runtime: JobRuntime,
) -> None:
    """After choosing host mode the CLI must fall back to the host's own login."""
    org = await seed_agent_org(app_sessions)
    await _save(client, org, auth_mode="api_key", api_key=API_KEY)

    await _save(client, org, auth_mode="host")
    env = await _agent_env(app_sessions, job_runtime, stage_claude, org)

    assert "ANTHROPIC_API_KEY" not in env
