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

"""The gate that stops a provider silently faking work it cannot do.

The failure this guards against is not a crash — it is a *plausible* success:
an agent that answers fluently about files it never read, or a scan that
reports zero features because its MCP writes never happened. Those look fine
in a log. So these tests assert the failure is loud.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.organization import AIProvider, Organization
from app.services.ai_runner import run_agent
from app.services.ai_runner.capabilities import capabilities_for
from app.services.ai_runner.capability_gate import adapt_config, unsupported_reason
from app.services.ai_runner.ollama_models import OLLAMA_HOST_ENV, OLLAMA_THINK_ENV
from app.services.claude_runner import (
    NO_REPO_CONTEXT,
    ClaudeRunnerConfig,
    ClaudeRunResult,
    MCPServerConfig,
)

REPO_DIR = "/tmp/some-repo"


def _org(provider: AIProvider, **kw: object) -> Organization:
    org = Organization(id=uuid.uuid4(), name="T", slug="t", ai_provider=provider)
    for key, value in kw.items():
        setattr(org, key, value)
    return org


def _mcp() -> MCPServerConfig:
    return MCPServerConfig(backend_url="http://x", mcp_token="t", tool_names=["get_features"])


# --- what a provider without files must refuse -------------------------------


def test_ollama_refuses_a_real_repo_path() -> None:
    """A repo path means "read these files" — Ollama cannot, so it must not try."""
    caps = capabilities_for(AIProvider.ollama)
    reason = unsupported_reason(caps, REPO_DIR, ClaudeRunnerConfig())
    assert reason is not None
    # The message reaches an operator in a job error, so it must name the
    # problem and the way out, not just fail.
    assert "cannot" in reason and "AI Config" in reason


def test_ollama_allows_the_no_repo_sentinel() -> None:
    """The pure-LLM callers pass the sentinel and must keep working."""
    caps = capabilities_for(AIProvider.ollama)
    assert unsupported_reason(caps, NO_REPO_CONTEXT, ClaudeRunnerConfig()) is None


def test_ollama_allows_mcp_tools() -> None:
    """Tools run in-process, so they are supported even without a filesystem."""
    caps = capabilities_for(AIProvider.ollama)
    cfg = ClaudeRunnerConfig(mcp=_mcp())
    assert unsupported_reason(caps, NO_REPO_CONTEXT, cfg) is None


def test_ollama_refuses_session_resume() -> None:
    """Stateless HTTP has no session to resume."""
    caps = capabilities_for(AIProvider.ollama)
    cfg = ClaudeRunnerConfig(is_resume=True, cli_session_id="abc")
    assert unsupported_reason(caps, NO_REPO_CONTEXT, cfg) is not None


def test_unlimited_turns_is_not_mistaken_for_single_turn() -> None:
    """max_turns == 0 means UNLIMITED, and the most agentic callers pass it.

    Gating on ``max_turns > 1`` would read those as single-turn and wave them
    through; the sentinel is what actually distinguishes them.
    """
    caps = capabilities_for(AIProvider.ollama)
    cfg = ClaudeRunnerConfig(max_turns=0)
    assert unsupported_reason(caps, REPO_DIR, cfg) is not None


@pytest.mark.parametrize("provider", [AIProvider.claude, AIProvider.copilot, AIProvider.codex])
def test_cli_providers_are_never_gated(provider: AIProvider) -> None:
    """Regression guard: the gate must not narrow the existing providers.

    All ~19 call sites run through it, so a false positive here would break
    features that work today.
    """
    caps = capabilities_for(provider)
    cfg = ClaudeRunnerConfig(mcp=_mcp(), is_resume=True, max_turns=0)
    assert unsupported_reason(caps, REPO_DIR, cfg) is None


# --- the gate is wired into the seam, not just importable --------------------


async def test_run_agent_fails_loudly_instead_of_returning_empty() -> None:
    """The whole point: a blocked run must not look like a successful empty one."""
    org = _org(AIProvider.ollama)
    with patch("app.services.ai_runner.provider_for") as provider_for:
        result = await run_agent(org, "summarise this repo", REPO_DIR)
        # The provider is never reached — no half-run, no partial side effects.
        provider_for.assert_not_called()
    assert result.success is False
    assert result.error and "cannot" in result.error
    assert result.output == ""


async def test_run_agent_still_dispatches_when_supported() -> None:
    org = _org(AIProvider.ollama)
    runner = AsyncMock(return_value=ClaudeRunResult(success=True, output="ok"))
    with patch("app.services.ai_runner.provider_for") as provider_for:
        provider_for.return_value.run = runner
        result = await run_agent(org, "classify this", NO_REPO_CONTEXT)
    assert result.success is True
    runner.assert_awaited_once()


# --- config adaptation -------------------------------------------------------


def test_org_settings_travel_per_run_not_via_process_env() -> None:
    """Two orgs in one process must not clobber each other's host.

    This is why the settings ride ``config.env_extra`` instead of os.environ —
    an implementation using the process env passes the single-org case and
    fails exactly here.
    """
    caps = capabilities_for(AIProvider.ollama)
    a = adapt_config(
        caps,
        _org(AIProvider.ollama, ai_base_url="http://a:11434", ai_thinking=True),
        ClaudeRunnerConfig(),
    )
    b = adapt_config(
        caps,
        _org(AIProvider.ollama, ai_base_url="http://b:11434", ai_thinking=False),
        ClaudeRunnerConfig(),
    )
    assert a.env_extra and a.env_extra[OLLAMA_HOST_ENV] == "http://a:11434"
    assert a.env_extra[OLLAMA_THINK_ENV] == "1"
    assert b.env_extra and b.env_extra[OLLAMA_HOST_ENV] == "http://b:11434"
    assert b.env_extra[OLLAMA_THINK_ENV] == "0"


def test_base_url_falls_back_to_the_table_default() -> None:
    """A NULL column means "use the default", resolved here rather than in the DB."""
    caps = capabilities_for(AIProvider.ollama)
    cfg = adapt_config(caps, _org(AIProvider.ollama, ai_base_url=None), ClaudeRunnerConfig())
    assert cfg.env_extra and cfg.env_extra[OLLAMA_HOST_ENV] == caps.default_base_url


def test_slow_provider_gets_more_time_and_fewer_turns() -> None:
    """Callers' limits assume a hosted API; local inference needs adapting.

    Done at the seam so the ~19 call sites keep their own numbers.
    """
    caps = capabilities_for(AIProvider.ollama)
    # quiz_batch_generation really does ask for 30 turns.
    cfg = adapt_config(caps, _org(AIProvider.ollama), ClaudeRunnerConfig(max_turns=30))
    assert cfg.max_turns == caps.max_turns_cap
    assert cfg.timeout_seconds > ClaudeRunnerConfig().timeout_seconds


def test_unlimited_turns_are_capped_not_honoured() -> None:
    """max_turns=0 (unlimited) on a small local model is a runaway risk."""
    caps = capabilities_for(AIProvider.ollama)
    cfg = adapt_config(caps, _org(AIProvider.ollama), ClaudeRunnerConfig(max_turns=0))
    assert cfg.max_turns == caps.max_turns_cap


def test_claude_config_is_passed_through_untouched() -> None:
    """No adaptation applies to a provider with no multiplier or cap."""
    caps = capabilities_for(AIProvider.claude)
    original = ClaudeRunnerConfig(max_turns=40, timeout_seconds=900)
    assert adapt_config(caps, _org(AIProvider.claude), original) is original
