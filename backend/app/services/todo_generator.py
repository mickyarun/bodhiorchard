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
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.schemas.bud_todo_generator import TodoGeneratorItem, TodoGeneratorPayload
from app.services.claude_runner import (
    ClaudeRunnerConfig,
    ProgressCallback,
    run_claude_code,
)
from app.services.event_bus import publish
from app.services.skill_loader import Skill, load_skill, load_skill_for_org

logger = structlog.get_logger(__name__)

# Single-shot: the agent receives the full tech spec + repo list and
# emits the YAML payload immediately. No tool calls — the spec already
# contains every file path the agent needs to surface in
# ``code_locations``. Keeping ``max_turns=1`` cuts wall-clock time from
# ~30s to ~5-10s and removes a class of "agent went exploring" failures.
#
# Output was JSON until we measured Sonnet spending most of the budget on
# JSON-syntax fidelity (escape quotes, balance braces) rather than the
# actual content. YAML cuts the per-item syntax tax dramatically while
# the Pydantic validator keeps the same shape contract.
#
# ``_TIMEOUT_FALLBACK_SECONDS`` is used only when the org's skill row has
# ``timeout_seconds = 0`` (the seed default). Admins can override the
# per-skill timeout via Settings → Agent Prompts.
_TIMEOUT_FALLBACK_SECONDS = 180
_AGENT_MAX_TURNS = 1
_SKILL_SLUG = "todo-generator"


class TodoGenerationError(RuntimeError):
    """Raised when the agent fails or returns an invalid payload."""


async def generate_todos_for_bud(
    bud: BUDDocument,
    impacted_repos: list[tuple[uuid.UUID, str]],
    *,
    reason: str = "initial",
    db: AsyncSession | None = None,
    org_id: uuid.UUID | None = None,
) -> list[TodoGeneratorItem]:
    """Run the ``todo-generator`` agent and return validated TODO items.

    Args:
        bud: The BUD whose ``tech_spec_md`` will drive the breakdown.
        impacted_repos: ``(repo_id, repo_name)`` pairs the spec touches.
        reason: ``"initial"`` (dev-phase transition) or ``"regenerate"``
            (user-triggered). Surfaced on the progress channel only.
        db: Async session for loading the org's customised skill (prompt,
            timeout, model). When omitted, falls back to the file-based
            skill defaults — kept for tests that don't wire a DB.
        org_id: Organisation UUID; required alongside ``db`` to resolve
            per-org skill overrides set via Settings → Agent Prompts.

    Raises:
        TodoGenerationError: If the agent fails, output is unparseable,
            or the payload violates :class:`TodoGeneratorPayload`'s
            length / shape caps.
    """
    bud_topic = f"todo:{bud.id}"
    _publish_progress(bud_topic, "generating_start", reason=reason)

    skill = await _resolve_skill(db, org_id)
    prompt = _build_prompt(bud, impacted_repos, skill)
    config = _build_config(skill)
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


async def _resolve_skill(db: AsyncSession | None, org_id: uuid.UUID | None) -> Skill:
    """Load the org-customised skill row, falling back to the file default.

    Tests that don't wire a DB still work because the file copy carries
    the same prompt + ``timeout_seconds: 0`` (which then resolves to the
    code-side ``_TIMEOUT_FALLBACK_SECONDS``).
    """
    if db is not None and org_id is not None:
        return await load_skill_for_org(_SKILL_SLUG, org_id, db)
    return load_skill(_SKILL_SLUG)


def _build_prompt(
    bud: BUDDocument,
    impacted_repos: list[tuple[uuid.UUID, str]],
    skill: Skill,
) -> str:
    """Compose the agent prompt: skill body + tech spec + repo list."""
    repo_lines = "\n".join(f"- {name}" for _, name in impacted_repos) or "- (no repos provided)"
    tech_spec = bud.tech_spec_md or "(empty tech spec)"
    return (
        f"{skill.prompt}\n\n"
        "## Available repos\n"
        f"{repo_lines}\n\n"
        "## Approved tech spec\n"
        f"{tech_spec}\n"
    )


def _build_config(skill: Skill) -> ClaudeRunnerConfig:
    """Build runner config: single turn, no tools, configurable timeout.

    The agent doesn't need to read files — every path it should surface
    is already in the tech spec we hand it. Locking ``allowed_tools=[]``
    forces it to emit JSON immediately rather than spending turns on
    ``Read``/``Grep`` exploration. ``timeout_seconds`` comes from the
    skill row (Settings → Agent Prompts), falling back to
    ``_TIMEOUT_FALLBACK_SECONDS`` when unset.
    """
    return ClaudeRunnerConfig(
        max_turns=_AGENT_MAX_TURNS,
        timeout_seconds=skill.timeout_or_default(_TIMEOUT_FALLBACK_SECONDS),
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
    """Extract YAML from the agent's output and validate against the schema."""
    parsed = _parse_yaml_response(raw_output)
    if parsed is None:
        raise TodoGenerationError("agent output contained no parseable YAML")
    try:
        payload = TodoGeneratorPayload.model_validate(parsed)
    except Exception as exc:
        raise TodoGenerationError(f"agent YAML failed schema validation: {exc}") from exc
    return payload.items


def _parse_yaml_response(output: str) -> dict[str, Any] | None:
    """Pull a YAML mapping out of an LLM response.

    The agent is instructed to emit a single fenced YAML block. Real-world
    output also sometimes ships bare (no fence) or wraps the fence with
    short prose, so we try three strategies in order:

      1. Direct ``yaml.safe_load`` on the trimmed output (bare YAML).
      2. Extract from a fenced block opened with `````yaml``.
      3. Extract from a generic three-backtick fence (model dropped the
         language tag).

    Returns the parsed mapping, or ``None`` if nothing in the output
    yields a top-level dict. We deliberately reject scalar / list roots —
    :class:`TodoGeneratorPayload` always validates against a dict.
    """
    text = output.strip()

    def _try_load(blob: str) -> dict[str, Any] | None:
        try:
            parsed = yaml.safe_load(blob)
        except yaml.YAMLError:
            return None
        return parsed if isinstance(parsed, dict) else None

    direct = _try_load(text)
    if direct is not None:
        return direct

    for fence_marker in ("```yaml", "```yml", "```"):
        if fence_marker not in text:
            continue
        try:
            start = text.index(fence_marker) + len(fence_marker)
            # Skip the rest of the opening line (any language tag remnants).
            newline = text.index("\n", start)
            end = text.index("```", newline)
        except ValueError:
            continue
        fenced = text[newline:end].strip()
        loaded = _try_load(fenced)
        if loaded is not None:
            return loaded
    return None
