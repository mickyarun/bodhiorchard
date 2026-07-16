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

"""Runs prompts against a local Ollama server, with an in-process tool loop.

For deployments that cannot install an agent CLI. Ollama exposes tool calling
over plain HTTP, and our MCP tools are already Python functions, so the loop is
just: ask -> if it wants tools, run them -> hand back the results -> repeat.

Limits are declared in the capability table rather than discovered here: no
filesystem, no session resume. ``run_agent`` refuses those before dispatch, so
this module can assume what it receives is runnable.
"""

import uuid
from pathlib import Path
from typing import Any

import structlog

from app.database import AsyncSessionLocal
from app.mcp.auth import MCPAuthResult
from app.models.organization import Organization
from app.services.ai_runner.ollama_chat import OllamaChatError, chat
from app.services.ai_runner.ollama_models import (
    OLLAMA_MODEL_ENV,
    OLLAMA_THINK_ENV,
    base_url_from_env,
)
from app.services.claude_runner import (
    ClaudeRunnerConfig,
    ClaudeRunResult,
    ProgressCallback,
)

logger = structlog.get_logger(__name__)

# A model that keeps calling tools without ever answering would otherwise spin
# until the timeout. run_agent already caps max_turns from the table; this is
# the floor if a caller somehow asks for nothing.
_MIN_TURNS = 1


class OllamaProvider:
    """Runs prompts via a local Ollama server's HTTP API."""

    async def run(
        self,
        prompt: str,
        working_dir: str | Path,
        config: ClaudeRunnerConfig | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> ClaudeRunResult:
        """Execute ``prompt``, running any tools the model asks for.

        ``working_dir`` is ignored — this provider has no filesystem, which the
        capability table declares and ``run_agent`` enforces, so a caller
        needing files never reaches here.
        """
        config = config or ClaudeRunnerConfig()
        env = config.env_extra or {}
        base_url = base_url_from_env(env)
        think = env.get(OLLAMA_THINK_ENV) == "1"
        # The org's model, NOT the skill's. Skill frontmatter names Claude
        # tiers ("sonnet", "haiku") which mean nothing to a local server and
        # would 404 — the installed set lives on the org's host, so the org
        # picks from it once.
        model = env.get(OLLAMA_MODEL_ENV, "")
        if config.model and config.model != model:
            logger.debug(
                "ollama_skill_model_ignored", skill_model=config.model, org_model=model or None
            )

        if not model:
            return ClaudeRunResult(
                success=False,
                output="",
                error=(
                    "No Ollama model chosen for this organisation. Pick one in "
                    "Settings -> AI Config (only models with the `tools` "
                    "capability can run agents)."
                ),
            )

        logger.info(
            "ollama_run_start",
            base_url=base_url,
            model=model,
            think=think,
            mcp_enabled=config.mcp is not None,
            max_turns=config.max_turns,
            prompt_preview=prompt[:100],
        )
        try:
            if config.mcp is None:
                return await self._single_shot(base_url, model, prompt, think, config)
            return await self._tool_loop(base_url, model, prompt, think, config, progress_callback)
        except OllamaChatError as exc:
            logger.error("ollama_run_failed", error=str(exc))
            return ClaudeRunResult(success=False, output="", error=str(exc))

    async def _single_shot(
        self,
        base_url: str,
        model: str,
        prompt: str,
        think: bool,
        config: ClaudeRunnerConfig,
    ) -> ClaudeRunResult:
        """One turn, no tools — the pure-LLM callers."""
        message = await chat(
            base_url,
            model,
            [{"role": "user", "content": prompt}],
            timeout_s=config.timeout_seconds,
            think=think,
            # Several callers parse strict JSON and fall back to a default on
            # failure. Asking Ollama to constrain the output makes the good
            # path much more likely on a small model.
            json_format=config.output_format == "json",
        )
        return ClaudeRunResult(success=True, output=str(message.get("content") or ""))

    async def _tool_loop(
        self,
        base_url: str,
        model: str,
        prompt: str,
        think: bool,
        config: ClaudeRunnerConfig,
        progress_callback: ProgressCallback | None,
    ) -> ClaudeRunResult:
        """Ask, run whatever tools the model calls, repeat until it answers."""
        # Imported here, not at module scope: app.mcp.server reaches back into
        # app.services.ai_runner (via handlers_hooks -> pr_auto_transition ->
        # bud_estimation -> estimation_llm), so a top-level import cycles
        # through a half-initialised module. Same reason streamable.py:337
        # does it. Verified, not assumed.
        from app.services.ai_runner.ollama_tools import (
            NoToolsRequestedError,
            build_tool_schemas,
            dispatch_tool,
            parse_tool_call,
        )

        assert config.mcp is not None  # guaranteed by run(); narrows for mypy
        if not config.mcp.org_id:
            # The CLI path resolves the org from the token on the backend side,
            # so a caller that predates org_id would leave it unset. Refuse
            # rather than run the tools against the wrong org — or none.
            return ClaudeRunResult(
                success=False,
                output="",
                error=(
                    "This feature's MCP config carries no organisation, so its tools cannot run."
                ),
            )
        try:
            tools = build_tool_schemas(config.mcp.tool_names)
        except NoToolsRequestedError as exc:
            return ClaudeRunResult(success=False, output="", error=str(exc))
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        turns = max(config.max_turns, _MIN_TURNS)

        async with AsyncSessionLocal() as db:
            org = await db.get(Organization, uuid.UUID(config.mcp.org_id))
            if org is None:
                return ClaudeRunResult(
                    success=False, output="", error="Organisation not found for this run"
                )
            # Handlers read their org from this, never from a token — so there
            # is nothing to mint, and no cross-process token to go stale.
            auth = MCPAuthResult(org=org, user=None)

            for _turn in range(turns):
                message = await chat(
                    base_url,
                    model,
                    messages,
                    timeout_s=config.timeout_seconds,
                    think=think,
                    tools=tools,
                )
                calls = message.get("tool_calls") or []
                if not calls:
                    return ClaudeRunResult(success=True, output=str(message.get("content") or ""))

                messages.append(message)
                for call in calls:
                    parsed = parse_tool_call(call)
                    if parsed is None:
                        continue
                    name, args = parsed
                    if progress_callback is not None:
                        progress_callback(name, {})
                    result = await dispatch_tool(db, auth, name, args)
                    messages.append({"role": "tool", "content": result})
                # Write tools flush through the handlers but never commit —
                # the caller owns the transaction, and here that is us.
                await db.commit()

        # Ran out of turns still calling tools. Say so rather than returning
        # the last tool result as if it were an answer.
        logger.warning("ollama_tool_loop_exhausted", turns=turns, model=model)
        return ClaudeRunResult(
            success=False,
            output="",
            error=(
                f"{model} kept calling tools without answering after {turns} turns. "
                f"A larger model may handle this task better."
            ),
        )
