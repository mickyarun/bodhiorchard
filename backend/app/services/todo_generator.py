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

"""Generate structured TODOs from an approved tech spec via the agent.

Calls the ``todo-generator`` skill, parses its JSON response, and
validates against :class:`TodoGeneratorPayload`. Publishes progress
events on the ``todo:{bud_id}`` channel so the UI can show a live
spinner + tool-use trail while the agent runs.

Pure I/O glue — has no opinions about how the resulting TODOs are
persisted. ``todo_sync.py`` consumes the items and writes them.
"""

import uuid
from typing import Any

import structlog

from app.models.bud import BUDDocument
from app.schemas.bud_todo_generator import TodoGeneratorItem, TodoGeneratorPayload
from app.services.claude_runner import (
    ClaudeRunnerConfig,
    ProgressCallback,
    run_claude_code,
)
from app.services.event_bus import publish
from app.services.json_parser import parse_json_response
from app.services.skill_loader import load_skill

logger = structlog.get_logger(__name__)

# Single-shot: the agent receives the full tech spec + repo list and
# emits the JSON payload immediately. No tool calls — the spec already
# contains every file path the agent needs to surface in
# ``code_locations``. Keeping ``max_turns=1`` cuts wall-clock time from
# ~30s to ~5-10s and removes a class of "agent went exploring" failures.
_AGENT_TIMEOUT_SECONDS = 90
_AGENT_MAX_TURNS = 1


class TodoGenerationError(RuntimeError):
    """Raised when the agent fails or returns an invalid payload."""


async def generate_todos_for_bud(
    bud: BUDDocument,
    impacted_repos: list[tuple[uuid.UUID, str]],
    *,
    reason: str = "initial",
) -> list[TodoGeneratorItem]:
    """Run the ``todo-generator`` agent and return validated TODO items.

    Args:
        bud: The BUD whose ``tech_spec_md`` will drive the breakdown.
        impacted_repos: ``(repo_id, repo_name)`` pairs the spec touches.
        reason: ``"initial"`` (dev-phase transition) or ``"regenerate"``
            (user-triggered). Surfaced on the progress channel only.

    Raises:
        TodoGenerationError: If the agent fails, output is unparseable,
            or the payload violates :class:`TodoGeneratorPayload`'s
            length / shape caps.
    """
    bud_topic = f"todo:{bud.id}"
    _publish_progress(bud_topic, "generating_start", reason=reason)

    prompt = _build_prompt(bud, impacted_repos)
    config = _build_config()
    progress_cb = _build_progress_callback(bud_topic)

    try:
        result = await run_claude_code(
            prompt=prompt,
            config=config,
            progress_callback=progress_cb,
        )
    except Exception as exc:
        _publish_progress(bud_topic, "generating_failed", error=str(exc))
        raise TodoGenerationError(f"agent run crashed: {exc}") from exc

    if not result.success or not result.output:
        _publish_progress(bud_topic, "generating_failed", error=result.error or "no output")
        raise TodoGenerationError(result.error or "agent returned no output")

    try:
        items = _parse_and_validate(result.output)
    except TodoGenerationError as exc:
        _publish_progress(bud_topic, "generating_failed", error=str(exc))
        raise

    _publish_progress(bud_topic, "generating_complete", count=len(items))
    logger.info(
        "todo_generator_done",
        bud_id=str(bud.id),
        reason=reason,
        count=len(items),
        cost_usd=result.cost_usd,
    )
    return items


def _build_prompt(bud: BUDDocument, impacted_repos: list[tuple[uuid.UUID, str]]) -> str:
    """Compose the agent prompt: skill body + tech spec + repo list."""
    skill = load_skill("todo-generator")
    repo_lines = "\n".join(f"- {name}" for _, name in impacted_repos) or "- (no repos provided)"
    tech_spec = bud.tech_spec_md or "(empty tech spec)"
    return (
        f"{skill.prompt}\n\n"
        "## Available repos\n"
        f"{repo_lines}\n\n"
        "## Approved tech spec\n"
        f"{tech_spec}\n"
    )


def _build_config() -> ClaudeRunnerConfig:
    """Build runner config: single turn, no tools, short timeout.

    The agent doesn't need to read files — every path it should surface
    is already in the tech spec we hand it. Locking ``allowed_tools=[]``
    forces it to emit JSON immediately rather than spending turns on
    ``Read``/``Grep`` exploration.
    """
    return ClaudeRunnerConfig(
        max_turns=_AGENT_MAX_TURNS,
        timeout_seconds=_AGENT_TIMEOUT_SECONDS,
        allowed_tools=[],
    )


def _build_progress_callback(topic: str) -> ProgressCallback:
    """Return a callback that forwards each agent tool_use to the WS topic."""

    def _on_tool_use(tool_name: str, _tool_input: dict[str, Any]) -> None:
        publish(topic, {"event": "generating_tool_use", "tool": tool_name})

    return _on_tool_use


def _publish_progress(topic: str, event: str, **fields: Any) -> None:
    """Publish a single progress event under ``todo:{bud_id}``."""
    payload: dict[str, Any] = {"event": event}
    payload.update(fields)
    publish(topic, payload)


def _parse_and_validate(raw_output: str) -> list[TodoGeneratorItem]:
    """Extract JSON, validate against :class:`TodoGeneratorPayload`."""
    parsed = parse_json_response(raw_output)
    if parsed is None:
        raise TodoGenerationError("agent output contained no parseable JSON")
    try:
        payload = TodoGeneratorPayload.model_validate(parsed)
    except Exception as exc:
        raise TodoGenerationError(f"agent JSON failed schema validation: {exc}") from exc
    return payload.items
