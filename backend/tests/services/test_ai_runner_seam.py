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

"""Unit tests for the AgentProvider seam.

These lock two contracts:
  1. ``provider_for`` resolves each org to its provider adapter (and Claude
     for ``None``), and ``run_agent`` delegates to the resolved adapter.
  2. ``run_agent_for_org_id`` loads the org then dispatches the same way.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.models.organization import AIProvider
from app.services import ai_runner
from app.services.ai_runner import provider_for, run_agent, run_agent_for_org_id
from app.services.ai_runner.claude_provider import ClaudeProvider
from app.services.ai_runner.codex_provider import CodexProvider
from app.services.ai_runner.copilot_provider import CopilotProvider
from app.services.claude_runner import ClaudeRunnerConfig, ClaudeRunResult


@asynccontextmanager
async def _fake_session() -> Any:
    """Async-CM stand-in so the org_id helper's session block never hits a DB."""
    yield object()


def _org(provider: AIProvider) -> SimpleNamespace:
    """A minimal org stand-in — ``provider_for`` only reads ``ai_provider``."""
    return SimpleNamespace(ai_provider=provider)


def test_provider_for_returns_claude_provider() -> None:
    """``None`` (and a claude org) resolves to the Claude provider."""
    assert isinstance(provider_for(None), ClaudeProvider)
    assert isinstance(provider_for(_org(AIProvider.claude)), ClaudeProvider)


def test_provider_for_dispatches_per_provider() -> None:
    """A codex / copilot org resolves to its own adapter, not Claude."""
    assert isinstance(provider_for(_org(AIProvider.codex)), CodexProvider)
    assert isinstance(provider_for(_org(AIProvider.copilot)), CopilotProvider)


async def test_run_agent_delegates_to_run_claude_code() -> None:
    """``run_agent`` forwards prompt/working_dir/config/callback verbatim."""
    expected = ClaudeRunResult(success=True, output="ok")
    config = ClaudeRunnerConfig(max_turns=3)

    def _cb(_tool: str, _inp: dict[str, object]) -> None:
        return None

    with patch.object(
        ai_runner.claude_provider,
        "run_claude_code",
        new=AsyncMock(return_value=expected),
    ) as rcc:
        result = await run_agent(None, "hello", "/tmp/repo", config, _cb)

    assert result is expected
    rcc.assert_awaited_once_with("hello", "/tmp/repo", config, _cb)


@pytest.mark.parametrize(
    "provider",
    [AIProvider.claude, AIProvider.codex, AIProvider.copilot],
)
async def test_run_agent_calls_resolved_provider(provider: AIProvider) -> None:
    """``run_agent`` routes to whichever adapter ``provider_for`` returns."""
    expected = ClaudeRunResult(success=True, output="routed")
    fake = AsyncMock(return_value=expected)
    config = ClaudeRunnerConfig(max_turns=1)

    with patch.object(ai_runner, "provider_for", return_value=SimpleNamespace(run=fake)):
        result = await run_agent(_org(provider), "p", "/repo", config)

    assert result is expected
    fake.assert_awaited_once_with("p", "/repo", config, None)


async def test_run_agent_for_org_id_loads_org_then_dispatches() -> None:
    """The org_id helper loads the org and forwards to ``run_agent``."""
    import uuid

    org = _org(AIProvider.codex)
    org_id = uuid.uuid4()
    expected = ClaudeRunResult(success=True, output="ok")

    fake_repo = AsyncMock()
    fake_repo.get_by_id = AsyncMock(return_value=org)

    with (
        patch.object(ai_runner, "AsyncSessionLocal", _fake_session),
        patch.object(ai_runner, "OrganizationRepository", return_value=fake_repo),
        patch.object(ai_runner, "run_agent", new=AsyncMock(return_value=expected)) as ra,
    ):
        result = await run_agent_for_org_id(org_id, "p", "/repo")

    assert result is expected
    fake_repo.get_by_id.assert_awaited_once_with(org_id)
    assert ra.await_args.args[0] is org


async def test_run_agent_for_org_id_none_skips_load() -> None:
    """A ``None`` org_id skips the DB load and falls back to Claude (org=None)."""
    expected = ClaudeRunResult(success=True, output="ok")
    with (
        patch.object(ai_runner, "OrganizationRepository") as repo,
        patch.object(ai_runner, "run_agent", new=AsyncMock(return_value=expected)) as ra,
    ):
        result = await run_agent_for_org_id(None, "p", "/repo")

    assert result is expected
    repo.assert_not_called()
    assert ra.await_args.args[0] is None
