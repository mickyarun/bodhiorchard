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
from app.services.ai_runner.capabilities import capabilities_for
from app.services.ai_runner.model_resolution import resolve_model
from app.services.claude_runner import (
    NO_REPO_CONTEXT,
    ClaudeRunnerConfig,
    MCPServerConfig,
    ProgressCallback,
)

# The one MCP tool synthesis drives: the model reads the cluster payload the
# prompt already carries and calls this per feature. A provider that runs tools
# in-process must be handed this name explicitly; the CLI providers see the
# full tool set (empty list) and also have file access for the optional
# "read a few files to split a cluster" step in the prompt.
_SYNTHESIS_TOOLS = ("write_synthesis_feature",)

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

    Feature counts come from the DB after the run, not from this object — the
    agent writes features inline via ``write_synthesis_feature`` calls, so the
    stage queries the DB to count them once the run is done.
    """

    success: bool
    error: str | None = None
    elapsed_s: float = 0.0
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw: dict[str, object] = field(default_factory=dict)
    # Which agent produced this, for the stage's error reporting. A run that
    # exits cleanly having written nothing is reported by the stage, and
    # naming the wrong provider there sends the reader after the wrong cause.
    provider: str = ""
    model: str = ""
    # The agent's own final message. Kept on success too, which is the case
    # that needs it: a run that wrote no features exits 0 with its reasoning
    # here, and that text is the only direct evidence of why. Truncated
    # because it is bound for a log line and an error string.
    output: str = ""


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
        provider = request.org.ai_provider if request.org is not None else AIProvider.claude
        caps = capabilities_for(provider)
        org_id = str(request.org.id) if request.org is not None else None

        # Synthesis is driven by write_synthesis_feature over the cluster
        # payload the prompt already carries — it does not need to read the
        # repository. A file-capable provider still gets the working_dir so it
        # can optionally Read a few files to split an ambiguous cluster; a
        # provider without file access (Ollama) runs the same synthesis from
        # the payload alone via the in-process tool loop, which requires the
        # tool named explicitly rather than the CLI's "empty means all".
        if caps.supports_files:
            working_dir = request.working_dir
            tool_names: list[str] = []
        else:
            working_dir = NO_REPO_CONTEXT
            tool_names = list(_SYNTHESIS_TOOLS)

        config = ClaudeRunnerConfig(
            max_turns=request.max_turns,
            timeout_seconds=request.timeout_seconds,
            output_format="json",
            mcp=MCPServerConfig(
                backend_url=request.mcp_backend_url,
                mcp_token=request.mcp_token,
                tool_names=tool_names,
                org_id=org_id,
            ),
        )
        # Report the model the provider will actually use, not the vestigial
        # ``request.model`` default (which never reaches the CLI — synthesis
        # runs on the provider's default model). Codex/Copilot drop a Claude
        # model id to their own default via ``resolve_model``.
        resolved_model, _ = resolve_model(provider, config.model, config.effort)
        logger.info(
            "scan_synthesis_starting",
            repo=request.repo_name,
            provider=provider.value,
            model=resolved_model or "(provider default)",
            max_turns=request.max_turns,
            reads_files=caps.supports_files,
        )
        result = await run_agent(
            request.org,
            request.prompt,
            working_dir,
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
            provider=provider.value,
            model=resolved_model or "(provider default)",
            output=(result.output or "")[:600],
        )
