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

"""Unit tests for the AgentProvider seam (Claude-only, Phase 1).

These lock the zero-behaviour-change contract: ``provider_for`` resolves to
the Claude provider, and ``run_agent`` delegates to ``run_claude_code`` with
the caller's arguments untouched.
"""

from unittest.mock import AsyncMock, patch

from app.services import ai_runner
from app.services.ai_runner import provider_for, run_agent
from app.services.ai_runner.claude_provider import ClaudeProvider
from app.services.claude_runner import ClaudeRunnerConfig, ClaudeRunResult


def test_provider_for_returns_claude_provider() -> None:
    """Every org currently resolves to the Claude provider."""
    assert isinstance(provider_for(None), ClaudeProvider)


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
