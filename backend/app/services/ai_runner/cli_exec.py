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

"""Shared subprocess runner for the Copilot / Codex provider adapters.

Batch-mode only (wait for full output): the provider CLIs emit JSONL we parse
after completion. Argument vectors are passed as a list to
``asyncio.create_subprocess_exec`` — no shell, so no shell-injection surface,
the same pattern ``claude_runner`` uses. Reuses the rlimits guard too.
"""

import asyncio
import contextlib
import os
import signal
from collections.abc import Callable
from pathlib import Path

import structlog

from app.services.claude_guard import apply_subprocess_rlimits
from app.services.claude_runner import _validate_working_dir

logger = structlog.get_logger(__name__)

# Provider JSONL lines can be large — the final ``agent_message`` carries the
# full generated artefact (e.g. a wireframe HTML), which blows past asyncio's
# 64KB default StreamReader limit. Matches ``claude_runner``'s streaming cap.
_STREAM_LINE_LIMIT = 10 * 1024 * 1024  # 10MB


def resolve_working_dir(working_dir: str | Path | None) -> str:
    """Validate + resolve a spawn cwd via the shared allowlist sanitizer.

    Public wrapper so provider adapters don't each import ``claude_runner``'s
    private ``_validate_working_dir``. Accepts ``NO_REPO_CONTEXT`` for
    pure-LLM calls. See ``claude_runner._validate_working_dir`` for the rules.
    """
    return _validate_working_dir(working_dir)


def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    """Best-effort kill the child's whole process group, then the child.

    ``apply_subprocess_rlimits`` runs ``os.setsid()`` so the CLI and its
    descendants (the MCP bridge, tool subprocesses) share one process group.
    Killing only the direct child would orphan those, so signal the group
    first. All failures (already-exited, no perms, non-POSIX) are ignored.
    """
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError, AttributeError):
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError):
        proc.kill()


async def run_cli(
    cmd: list[str],
    cwd: str | Path,
    env: dict[str, str],
    timeout_seconds: int,
) -> tuple[int, str, str]:
    """Run ``cmd`` to completion; return ``(returncode, stdout, stderr)``.

    Raises ``TimeoutError`` if the process exceeds ``timeout_seconds`` (the
    caller maps that to a failed run result). On timeout the whole process
    group is killed so the MCP bridge / tool subprocesses don't orphan.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        preexec_fn=apply_subprocess_rlimits(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        _kill_process_tree(proc)
        await proc.wait()
        raise
    return (
        proc.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


async def run_cli_streaming(
    cmd: list[str],
    cwd: str | Path,
    env: dict[str, str],
    timeout_seconds: int,
    on_line: Callable[[str], None],
) -> tuple[int, str, str]:
    """Like :func:`run_cli`, but stream stdout line-by-line to ``on_line``.

    Reads stdout incrementally so the caller can surface live progress (tool
    calls) instead of waiting for the whole run to finish. ``on_line`` is
    invoked with each decoded stdout line and must be cheap; it's wrapped so a
    raising callback can never break the reader. Same return shape and
    timeout/kill-the-process-group contract as :func:`run_cli`. A line beyond
    the 10MB buffer stops line-parsing (rare — only a multi-MB final message);
    stdout captured up to that point is still returned.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=_STREAM_LINE_LIMIT,
        preexec_fn=apply_subprocess_rlimits(),
    )
    out_chunks: list[str] = []
    err_chunks: list[str] = []

    async def _pump_stdout() -> None:
        assert proc.stdout is not None  # noqa: S101
        while True:
            try:
                raw = await proc.stdout.readline()
            except ValueError:
                logger.warning("cli_stream_line_overflow", limit_mb=10)
                break
            if not raw:
                break
            text = raw.decode("utf-8", errors="replace")
            out_chunks.append(text)
            try:
                on_line(text)
            except Exception:  # noqa: BLE001 — never break the reader
                logger.exception("cli_stream_on_line_failed")

    async def _pump_stderr() -> None:
        assert proc.stderr is not None  # noqa: S101
        data = await proc.stderr.read()
        err_chunks.append(data.decode("utf-8", errors="replace"))

    try:
        await asyncio.wait_for(
            asyncio.gather(_pump_stdout(), _pump_stderr()), timeout=timeout_seconds
        )
        await proc.wait()
    except TimeoutError:
        _kill_process_tree(proc)
        await proc.wait()
        raise
    return proc.returncode or 0, "".join(out_chunks), "".join(err_chunks)
