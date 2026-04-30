# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Synthesis runner — Strategy pattern over Claude invocation.

``SynthesisEngine`` is a thin Protocol so we can swap the underlying
client without touching the stage. The default implementation is
``ClaudeCodeEngine``, which reuses the existing ``run_claude_code``
subprocess wrapper (handles both api_key and hybrid_host auth modes).

A future ``AnthropicSDKEngine`` could call the Anthropic SDK directly
for sandbox previews; same interface, different transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import structlog

from app.services.claude_runner import (
    ClaudeRunnerConfig,
    MCPServerConfig,
    run_claude_code,
)

logger = structlog.get_logger(__name__)

# Default model for v2 synthesis. Single source of truth — the API
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


class ClaudeCodeEngine:
    """Default engine — spawns ``claude`` subprocess via ``run_claude_code``.

    Honours the org's claude_auth_mode (api_key vs hybrid_host) because
    ``run_claude_code`` reads from the process env that
    ``apply_claude_auth_to_env`` populates at startup.
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
        logger.info(
            "scan_synthesis_starting",
            repo=request.repo_name,
            model=request.model,
            max_turns=request.max_turns,
        )
        result = await run_claude_code(
            prompt=request.prompt,
            working_dir=request.working_dir,
            config=config,
        )
        return SynthesisOutcome(
            success=bool(result.success),
            error=result.error if not result.success else None,
            elapsed_s=getattr(result, "elapsed_s", 0.0) or 0.0,
            cost_usd=getattr(result, "cost_usd", None),
            input_tokens=getattr(result, "input_tokens", None),
            output_tokens=getattr(result, "output_tokens", None),
        )
