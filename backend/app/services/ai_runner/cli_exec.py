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
from pathlib import Path

import structlog

from app.services.claude_guard import apply_subprocess_rlimits
from app.services.claude_runner import _validate_working_dir

logger = structlog.get_logger(__name__)


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
