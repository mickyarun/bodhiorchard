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

"""OpenAI Codex CLI provider.

Runs ``codex exec --json`` headlessly under a read-only sandbox with
``approval_policy=never`` (so MCP tool calls don't auto-cancel in
non-interactive mode), wires the bodhiorchard MCP bridge via ``-c
mcp_servers.*`` overrides, and normalizes Codex's JSONL stream into a
``ClaudeRunResult`` (result = last ``item.completed`` ``agent_message``).
"""

import json
from pathlib import Path
from typing import Any

import structlog

from app.models.organization import AIProvider
from app.services.ai_runner.capabilities import resolve_model
from app.services.ai_runner.cli_exec import resolve_working_dir, run_cli, run_cli_streaming
from app.services.ai_runner.mcp_config import build_codex_mcp
from app.services.ai_runner.subprocess_env import build_provider_env
from app.services.claude_runner import (
    ClaudeRunnerConfig,
    ClaudeRunResult,
    ProgressCallback,
)

logger = structlog.get_logger(__name__)


def _compose_prompt(prompt: str, system_prompt_files: list[str]) -> str:
    """Prepend any system-prompt file contents to the prompt.

    Codex takes a single positional prompt; inline the files ahead of it
    (a missing/unreadable file is skipped + logged).
    """
    parts: list[str] = []
    for spf in system_prompt_files:
        try:
            parts.append(Path(spf).read_text(encoding="utf-8"))
        except OSError:
            logger.warning("codex_system_prompt_file_unreadable", path=spf)
    parts.append(prompt)
    return "\n\n".join(parts)


# Codex ``item`` types that are the agent thinking/answering, not an action —
# these don't count as "tool activity" for progress purposes.
_NON_TOOL_ITEMS = frozenset({"agent_message", "reasoning", "todo_list"})


def _tool_label(item: dict[str, Any]) -> str | None:
    """Derive a progress label from a Codex ``item`` object, or None.

    Codex emits ``item.started`` events as it runs actions. MCP tool calls,
    shell commands, and file edits are surfaced under friendly names; the
    agent's own message/reasoning items are skipped.
    """
    itype = item.get("type")
    if not isinstance(itype, str) or itype in _NON_TOOL_ITEMS:
        return None
    if itype == "mcp_tool_call":
        tool = item.get("tool") or item.get("name")
        server = item.get("server")
        if server and tool:
            return f"{server}-{tool}"
        return str(tool) if tool else "mcp_tool_call"
    if itype == "command_execution":
        return "shell"
    if itype == "file_change":
        return "edit"
    # Any other action-ish item type surfaces under its own name.
    return itype


def _emit_progress(line: str, callback: ProgressCallback) -> None:
    """Fire ``callback`` for a Codex tool/action item as it starts.

    Parses one JSONL line; a non-JSON or non-``item.started`` line is a no-op.
    Never raises — the streaming reader wraps this, but stay defensive anyway.
    """
    line = line.strip()
    if not line:
        return
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return
    if not isinstance(event, dict) or event.get("type") != "item.started":
        return
    item = event.get("item")
    if not isinstance(item, dict):
        return
    label = _tool_label(item)
    if label:
        callback(label, {})


def _parse_output(stdout: str) -> str:
    """Extract the final agent message from Codex's JSONL stream.

    The answer is the last ``item.completed`` whose ``item.type`` is
    ``agent_message``. Non-JSON / other event lines are ignored.
    """
    result_text = ""
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "item.completed":
            item = event.get("item")
            # ``item`` can be null / non-dict on a malformed or version-drifted
            # event — guard so ``_parse_output`` (called outside run()'s
            # try/except) can't raise and escape the run's error handling.
            if isinstance(item, dict) and item.get("type") == "agent_message" and item.get("text"):
                result_text = item["text"]
    return result_text


class CodexProvider:
    """Runs prompts via the OpenAI Codex CLI (``codex exec``)."""

    async def run(
        self,
        prompt: str,
        working_dir: str | Path,
        config: ClaudeRunnerConfig | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> ClaudeRunResult:
        """Execute ``prompt`` via ``codex exec`` and normalize the result.

        When ``progress_callback`` is supplied, stdout is streamed line-by-line
        and the callback fires on each Codex tool/action item as it starts, so
        callers (scan timeline, design tab) show live activity instead of a
        static spinner. Without it, the run is buffered.
        """
        config = config or ClaudeRunnerConfig()
        cwd = resolve_working_dir(working_dir)
        model, effort = resolve_model(AIProvider.codex, config.model, config.effort)

        cmd: list[str] = [
            "codex",
            "exec",
            "--json",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "-c",
            'approval_policy="never"',
            "-C",
            cwd,
        ]
        if model:
            cmd += ["-m", model]
        if effort:
            cmd += ["-c", f'model_reasoning_effort="{effort}"']

        mcp = build_codex_mcp(config.mcp)
        cmd += mcp.args

        # Codex takes a single positional prompt, after all options.
        cmd.append(_compose_prompt(prompt, config.system_prompt_files))

        env = build_provider_env(AIProvider.codex, config.env_extra)
        logger.info(
            "codex_run_start",
            cwd=cwd,
            model=model,
            effort=effort,
            mcp_enabled=config.mcp is not None,
            prompt_preview=prompt[:100],
        )
        try:
            if progress_callback is not None:
                cb = progress_callback

                def _on_line(line: str) -> None:
                    _emit_progress(line, cb)

                returncode, stdout, stderr = await run_cli_streaming(
                    cmd, cwd, env, config.timeout_seconds, _on_line
                )
            else:
                returncode, stdout, stderr = await run_cli(cmd, cwd, env, config.timeout_seconds)
        except (TimeoutError, OSError) as exc:
            logger.error("codex_run_error", error=str(exc))
            return ClaudeRunResult(success=False, output="", error=f"Codex CLI failed: {exc}")

        if returncode != 0:
            logger.error("codex_run_failed", returncode=returncode, stderr=stderr[:300])
            return ClaudeRunResult(
                success=False,
                output=stdout,
                error=stderr[:500] or f"Codex CLI exited with code {returncode}",
            )

        result_text = _parse_output(stdout)
        return ClaudeRunResult(success=True, output=result_text or stdout)
