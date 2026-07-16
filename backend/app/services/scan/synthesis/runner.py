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

"""Synthesis runner — Strategy pattern over the agent invocation.

``SynthesisEngine`` is a thin Protocol so we can swap the underlying
client without touching the stage. The default implementation is
``AgentCliEngine``, which routes through ``run_agent`` so the org's
selected provider (Claude / Copilot / Codex) runs the synthesis — auth
and MCP are handled per-provider inside the adapter.

A future ``AnthropicSDKEngine`` could call the Anthropic SDK directly
for sandbox previews; same interface, different transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import structlog

from app.models.organization import AIProvider, Organization
from app.services.ai_runner import run_agent
from app.services.ai_runner.model_resolution import resolve_model
from app.services.claude_runner import (
    ClaudeRunnerConfig,
    MCPServerConfig,
    ProgressCallback,
)

logger = structlog.get_logger(__name__)

# Default model for synthesis. Single source of truth — the API
# config endpoint reads this so the frontend doesn't duplicate the literal.
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TURNS = 40
DEFAULT_TIMEOUT_SECONDS = 300


@dataclass(slots=True, frozen=True)
class SynthesisRequest:
    """Inputs the engine needs to run one synthesis call."""

    prompt: str
    working_dir: str
    repo_name: str
    mcp_backend_url: str
    mcp_token: str
    model: str = DEFAULT_MODEL
    max_turns: int = DEFAULT_MAX_TURNS
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    # Optional per-tool-use observer. When provided, the run auto-switches
    # to ``stream-json`` so tool calls surface in real time instead of
    # being buffered until subprocess exit. Sync signature — see
    # ``claude_runner._find_tool_uses``.
    progress_callback: ProgressCallback | None = None
    # The org whose provider (Claude / Copilot / Codex) runs this
    # synthesis. ``None`` falls back to Claude — see ``run_agent``.
    org: Organization | None = None


@dataclass(slots=True)
class SynthesisOutcome:
    """What the engine returns to the stage.

    Feature counts come from the DB after the run, not from this object —
    Claude writes features inline via ``write_synthesis_feature`` MCP
    calls, so the stage queries the DB to count them once Claude is done.
    """

    success: bool
    error: str | None = None
    elapsed_s: float = 0.0
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw: dict[str, object] = field(default_factory=dict)


class SynthesisEngine(Protocol):
    """Pluggable interface for invoking Claude with the synthesis prompt."""

    async def run(self, request: SynthesisRequest) -> SynthesisOutcome:  # pragma: no cover
        ...


class AgentCliEngine:
    """Default engine — routes through ``run_agent`` so the org's selected
    provider (Claude / Copilot / Codex) runs the synthesis.

    Auth and per-provider MCP wiring live inside the adapter; the org's
    credential is already in the process env via ``apply_claude_auth_to_env``.
    A ``None`` org falls back to Claude (see ``run_agent``).
    """

    async def run(self, request: SynthesisRequest) -> SynthesisOutcome:
        config = ClaudeRunnerConfig(
            max_turns=request.max_turns,
            timeout_seconds=request.timeout_seconds,
            output_format="json",
            mcp=MCPServerConfig(
                backend_url=request.mcp_backend_url,
                mcp_token=request.mcp_token,
            ),
        )
        # Report the model the provider will actually use, not the vestigial
        # ``request.model`` default (which never reaches the CLI — synthesis
        # runs on the provider's default model). Codex/Copilot drop a Claude
        # model id to their own default via ``resolve_model``.
        provider = request.org.ai_provider if request.org is not None else AIProvider.claude
        resolved_model, _ = resolve_model(provider, config.model, config.effort)
        logger.info(
            "scan_synthesis_starting",
            repo=request.repo_name,
            provider=provider.value,
            model=resolved_model or "(provider default)",
            max_turns=request.max_turns,
        )
        result = await run_agent(
            request.org,
            request.prompt,
            request.working_dir,
            config,
            request.progress_callback,
        )
        return SynthesisOutcome(
            success=bool(result.success),
            error=result.error if not result.success else None,
            elapsed_s=getattr(result, "elapsed_s", 0.0) or 0.0,
            cost_usd=getattr(result, "cost_usd", None),
            input_tokens=getattr(result, "input_tokens", None),
            output_tokens=getattr(result, "output_tokens", None),
        )
