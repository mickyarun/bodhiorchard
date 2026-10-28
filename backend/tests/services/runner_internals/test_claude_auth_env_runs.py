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

"""An org's auth mode, applied to the process, as the agent CLI actually receives it.

Each test applies an org's choice with ``apply_claude_auth_to_env`` and then
spawns the CLI through the real ``run_claude_code``; ``fake_claude.runs[i].env``
is the environment the child process was handed after the guard's filter.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt_secret
from app.models.organization import AIProvider, Organization
from app.services import claude_env
from app.services.claude_env import (
    CREDENTIAL_AUTH_MODES,
    apply_claude_auth_to_env,
    load_claude_env_at_startup,
)
from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript
from tests.services.runner_internals.log_tap import LogTap, everything_logged

API_KEY = "sk-ant-api03-runner-internals-secret"
OAUTH = "sk-ant-oat01-runner-internals-token"


def _org(mode: str, secret: str | None, provider: AIProvider = AIProvider.claude) -> Organization:
    return Organization(
        ai_provider=provider,
        claude_auth_mode=mode,
        claude_api_key_encrypted=encrypt_secret(secret) if secret else None,
    )


async def _run(fake: FakeClaudeRunner, tmp_path: Path) -> dict[str, str]:
    fake.enqueue(AgentScript.ok("done"))
    result = await run_claude_code("p", tmp_path, ClaudeRunnerConfig(timeout_seconds=5))
    assert result.success is True
    return fake.runs[-1].env


async def test_api_key_mode_reaches_the_cli_and_no_log_line(
    fake_claude: FakeClaudeRunner,
    clean_cred_env: LogTap,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The child gets the key and none of the backend's own secrets; no captured log has it."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:dbpass@db/app")
    apply_claude_auth_to_env(_org("api_key", API_KEY))

    env = await _run(fake_claude, tmp_path)

    assert env["ANTHROPIC_API_KEY"] == API_KEY
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert "DATABASE_URL" not in env
    assert not any(API_KEY in arg for arg in fake_claude.runs[0].argv)
    events = clean_cred_env.events()
    assert {"ai_env_credential_applied", "claude_run_start", "claude_run_complete"} <= set(events)
    assert API_KEY not in everything_logged(clean_cred_env, caplog, capsys)


async def test_switching_to_subscription_swaps_the_credential_between_runs(
    fake_claude: FakeClaudeRunner,
    clean_cred_env: LogTap,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """api_key → subscription: the second run sees only the OAuth token."""
    caplog.set_level(logging.DEBUG)
    apply_claude_auth_to_env(_org("api_key", API_KEY))
    first = await _run(fake_claude, tmp_path)
    apply_claude_auth_to_env(_org("subscription", OAUTH))
    second = await _run(fake_claude, tmp_path)

    assert (first.get("ANTHROPIC_API_KEY"), first.get("CLAUDE_CODE_OAUTH_TOKEN")) == (
        API_KEY,
        None,
    )
    assert (second.get("ANTHROPIC_API_KEY"), second.get("CLAUDE_CODE_OAUTH_TOKEN")) == (
        None,
        OAUTH,
    )
    logged = everything_logged(clean_cred_env, caplog, capsys)
    assert API_KEY not in logged and OAUTH not in logged


@pytest.mark.usefixtures("clean_cred_env")
async def test_switching_provider_clears_the_claude_key_and_hides_the_new_one(
    fake_claude: FakeClaudeRunner, tmp_path: Path
) -> None:
    """Claude → Codex: the Anthropic key is gone and the OpenAI key never reaches ``claude``."""
    apply_claude_auth_to_env(_org("api_key", API_KEY))
    apply_claude_auth_to_env(_org("api_key", "sk-openai-key", provider=AIProvider.codex))

    env = await _run(fake_claude, tmp_path)

    assert os.environ["OPENAI_API_KEY"] == "sk-openai-key"
    assert "ANTHROPIC_API_KEY" not in os.environ
    assert "ANTHROPIC_API_KEY" not in env and "OPENAI_API_KEY" not in env


async def test_corrupt_secret_falls_back_to_the_host_credential(
    fake_claude: FakeClaudeRunner,
    clean_cred_env: LogTap,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An undecryptable secret keeps the compose key and drops a stale OAuth token."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-compose-key")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "stale-oauth")
    org = Organization(
        ai_provider=AIProvider.claude,
        claude_auth_mode="api_key",
        claude_api_key_encrypted="enc:not-a-fernet-token",
    )

    apply_claude_auth_to_env(org)
    env = await _run(fake_claude, tmp_path)

    assert env.get("ANTHROPIC_API_KEY") == "sk-compose-key"
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert {"decrypt_secret_failed", "ai_env_host_mode"} <= set(clean_cred_env.events())


async def test_credential_mode_without_a_stored_secret_acts_as_host(
    fake_claude: FakeClaudeRunner, clean_cred_env: LogTap, tmp_path: Path
) -> None:
    """subscription mode with nothing stored clears the injected token instead of keeping it."""
    apply_claude_auth_to_env(_org("subscription", OAUTH))
    apply_claude_auth_to_env(_org("subscription", None))

    env = await _run(fake_claude, tmp_path)

    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert clean_cred_env.events().count("ai_env_host_mode") == 1


class _StubOrgRepo:
    """Stands in for ``OrganizationRepository`` in the startup loader."""

    found: Organization | None = None
    modes: list[Any] = []

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_first_with_stored_claude_credential(self, modes: Any) -> Organization | None:
        _StubOrgRepo.modes.append(modes)
        return _StubOrgRepo.found


@pytest.mark.parametrize("stored", [True, False])
async def test_startup_loader_applies_the_stored_credential_or_leaves_the_env(
    clean_cred_env: LogTap, monkeypatch: pytest.MonkeyPatch, stored: bool
) -> None:
    """Boot applies the first credentialed org; with none, the env is left alone."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-compose-key")
    monkeypatch.setattr(_StubOrgRepo, "found", _org("subscription", OAUTH) if stored else None)
    monkeypatch.setattr(_StubOrgRepo, "modes", [])
    monkeypatch.setattr(claude_env, "OrganizationRepository", _StubOrgRepo)

    await load_claude_env_at_startup(cast(AsyncSession, None))

    assert _StubOrgRepo.modes == [CREDENTIAL_AUTH_MODES]
    if stored:
        assert os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") == OAUTH
        assert "ANTHROPIC_API_KEY" not in os.environ
    else:
        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-compose-key"
        assert "claude_env_startup_no_stored_key" in clean_cred_env.events()
