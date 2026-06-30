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

"""Unit tests for the Codex adapter + cross-provider conformance."""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.organization import AIProvider, Organization
from app.services.ai_runner import codex_provider as cx
from app.services.ai_runner.codex_provider import CodexProvider
from app.services.ai_runner.copilot_provider import CopilotProvider
from app.services.ai_runner.registry import provider_for
from app.services.claude_runner import NO_REPO_CONTEXT, ClaudeRunnerConfig, ClaudeRunResult

_SAMPLE_JSONL = "\n".join(
    [
        '{"type":"thread.started","thread_id":"t1"}',
        '{"type":"item.completed","item":{"id":"i0","type":"reasoning","text":"thinking"}}',
        '{"type":"item.completed","item":{"id":"i1","type":"agent_message","text":"CODEX FINAL"}}',
        '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":2}}',
    ]
)


def test_parse_output_takes_last_agent_message() -> None:
    assert cx._parse_output(_SAMPLE_JSONL) == "CODEX FINAL"


def test_parse_output_ignores_non_agent_items() -> None:
    only_reasoning = '{"type":"item.completed","item":{"type":"reasoning","text":"x"}}'
    assert cx._parse_output(only_reasoning) == ""


def test_registry_dispatches_codex() -> None:
    assert isinstance(provider_for(Organization(ai_provider=AIProvider.codex)), CodexProvider)


async def test_codex_run_parses_success() -> None:
    config = ClaudeRunnerConfig(timeout_seconds=30)
    with patch.object(cx, "run_cli", new=AsyncMock(return_value=(0, _SAMPLE_JSONL, ""))):
        result = await CodexProvider().run("hi", NO_REPO_CONTEXT, config)
    assert result.success is True
    assert result.output == "CODEX FINAL"
    assert result.cost_usd is None


async def test_codex_run_reports_failure() -> None:
    config = ClaudeRunnerConfig(timeout_seconds=30)
    with patch.object(cx, "run_cli", new=AsyncMock(return_value=(2, "", "kaboom"))):
        result = await CodexProvider().run("hi", NO_REPO_CONTEXT, config)
    assert result.success is False
    assert "kaboom" in (result.error or "")


@pytest.mark.parametrize("provider", [AIProvider.copilot, AIProvider.codex])
async def test_provider_conformance_returns_runresult(provider: AIProvider) -> None:
    """Each non-Claude provider returns a normalized ClaudeRunResult with
    unsupported fields (cost_usd) left None rather than raising."""
    impl = provider_for(Organization(ai_provider=provider))
    assert isinstance(impl, (CopilotProvider, CodexProvider))
    module = cx if provider == AIProvider.codex else __import__(
        "app.services.ai_runner.copilot_provider", fromlist=["run_cli"]
    )
    with patch.object(module, "run_cli", new=AsyncMock(return_value=(0, "", ""))):
        result = await impl.run("ping", NO_REPO_CONTEXT, ClaudeRunnerConfig(timeout_seconds=5))
    assert isinstance(result, ClaudeRunResult)
    assert result.cost_usd is None
    assert result.turns_used is None
