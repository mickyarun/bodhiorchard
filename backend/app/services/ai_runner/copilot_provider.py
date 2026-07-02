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

"""GitHub Copilot CLI provider.

Runs ``copilot -p`` headlessly, wires the bodhiorchard MCP bridge via
``--additional-mcp-config``, and normalizes Copilot's JSONL event stream into
a ``ClaudeRunResult``. Copilot exposes no per-call cost, so ``cost_usd`` is
left ``None``; the result text is the last ``assistant.message`` content.
"""

import contextlib
import json
import os
from pathlib import Path

import structlog

from app.models.organization import AIProvider
from app.services.ai_runner.capabilities import resolve_model
from app.services.ai_runner.cli_exec import resolve_working_dir, run_cli, run_cli_streaming
from app.services.ai_runner.mcp_config import build_copilot_mcp
from app.services.ai_runner.subprocess_env import build_provider_env
from app.services.claude_runner import (
    ClaudeRunnerConfig,
    ClaudeRunResult,
    ProgressCallback,
)

logger = structlog.get_logger(__name__)


def _compose_prompt(prompt: str, system_prompt_files: list[str]) -> str:
    """Prepend any system-prompt file contents to the prompt.

    Copilot has no ``--append-system-prompt-file`` flag, so we inline the
    files ahead of the prompt (a missing/unreadable file is skipped + logged).
    """
    parts: list[str] = []
    for spf in system_prompt_files:
        try:
            parts.append(Path(spf).read_text(encoding="utf-8"))
        except OSError:
            logger.warning("copilot_system_prompt_file_unreadable", path=spf)
    parts.append(prompt)
    return "\n\n".join(parts)


def _emit_progress(line: str, callback: ProgressCallback) -> None:
    """Fire ``callback`` for a Copilot tool-invocation event as it starts.

    Copilot's JSONL marks tool activity with an event ``type`` containing
    ``tool`` (e.g. ``tool.execution``); the tool name lives in ``data.name`` /
    ``data.tool``. Result/output events are skipped so a call doesn't tick
    twice. Best-effort by design — an unrecognised shape is simply ignored.
    """
    line = line.strip()
    if not line:
        return
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return
    if not isinstance(event, dict):
        return
    etype = event.get("type")
    if not isinstance(etype, str):
        return
    low = etype.lower()
    if "tool" not in low or any(k in low for k in ("result", "response", "output", "completed")):
        return
    raw_data = event.get("data")
    data = raw_data if isinstance(raw_data, dict) else {}
    name = data.get("name") or data.get("tool") or event.get("name") or etype
    callback(str(name), {})


def _parse_output(stdout: str) -> str:
    """Extract the final assistant text from Copilot's JSONL stream.

    The last ``assistant.message`` event's ``data.content`` is the answer.
    Lines that aren't JSON (or aren't the events we want) are ignored.
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
        if isinstance(event, dict) and event.get("type") == "assistant.message":
            # ``data`` can be null even when the key exists (so ``.get("data", {})``
            # wouldn't help) — guard so ``_parse_output`` (called outside run()'s
            # try/except) can't raise on a version-drifted event shape.
            data = event.get("data")
            content = data.get("content") if isinstance(data, dict) else None
            if content:
                result_text = content
    return result_text


class CopilotProvider:
    """Runs prompts via the GitHub Copilot CLI (``copilot``)."""

    async def run(
        self,
        prompt: str,
        working_dir: str | Path,
        config: ClaudeRunnerConfig | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> ClaudeRunResult:
        """Execute ``prompt`` via ``copilot -p`` and normalize the result.

        When ``progress_callback`` is supplied, stdout is streamed and the
        callback fires on each Copilot tool invocation as it starts, so callers
        show live activity instead of a static spinner. Without it, the run is
        buffered.
        """
        config = config or ClaudeRunnerConfig()
        cwd = resolve_working_dir(working_dir)
        model, effort = resolve_model(AIProvider.copilot, config.model, config.effort)

        cmd: list[str] = [
            "copilot",
            "-p",
            _compose_prompt(prompt, config.system_prompt_files),
            "--output-format",
            "json",
            "--allow-all-tools",
            "--no-ask-user",
            "--no-auto-update",
            "--log-level",
            "error",
            "-C",
            cwd,
        ]
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["--reasoning-effort", effort]

        mcp = build_copilot_mcp(config.mcp)
        cmd += mcp.args

        env = build_provider_env(AIProvider.copilot, config.env_extra)
        logger.info(
            "copilot_run_start",
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
            logger.error("copilot_run_error", error=str(exc))
            return ClaudeRunResult(success=False, output="", error=f"Copilot CLI failed: {exc}")
        finally:
            for path in mcp.cleanup_paths:
                with contextlib.suppress(OSError):
                    os.unlink(path)

        if returncode != 0:
            logger.error("copilot_run_failed", returncode=returncode, stderr=stderr[:300])
            return ClaudeRunResult(
                success=False,
                output=stdout,
                error=stderr[:500] or f"Copilot CLI exited with code {returncode}",
            )

        result_text = _parse_output(stdout)
        return ClaudeRunResult(success=True, output=result_text or stdout)
