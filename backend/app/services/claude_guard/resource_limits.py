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

"""Kernel-enforced resource limits for the ``claude`` subprocess.

The wall-clock ``timeout_seconds`` knob on ``ClaudeRunnerConfig`` kills the
subprocess if it runs too long, but it does nothing about a compromised
subprocess that allocates 64 GiB of RAM or forks 100k workers before the
timeout fires (classic crypto-miner / fork-bomb patterns seen in real
prompt-injection incidents).

This module returns a ``preexec_fn`` callable that runs between ``fork``
and ``exec`` and applies ``RLIMIT_AS`` (address space) plus ``RLIMIT_NPROC``
(per-user process count). Limits are intentionally generous — they are
last-line insurance, not tight policy — and only fire on pathological
behavior.
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Callable

# 8 GiB virtual address space. Claude with large prompt-cache + stream-json
# buffer comfortably fits in 1-2 GiB; 8 GiB allows headroom for a worktree
# checkout, npm-cache reads, and a generous safety margin. Set tighter only
# after observing real-world memory profiles.
_DEFAULT_ADDRESS_SPACE_BYTES: int = 8 * 1024 * 1024 * 1024

# Per-user process cap. Fork-bomb defense: if the subprocess goes feral and
# starts spawning workers, the kernel refuses past this count. 512 is well
# above any legitimate ``claude`` workload (it occasionally spawns Node for
# MCP plus a handful of git invocations).
_DEFAULT_PROCESS_CAP: int = 512


def apply_subprocess_rlimits(
    address_space_bytes: int = _DEFAULT_ADDRESS_SPACE_BYTES,
    process_cap: int = _DEFAULT_PROCESS_CAP,
) -> Callable[[], None] | None:
    """Return a ``preexec_fn`` for ``subprocess`` / ``asyncio`` spawn calls.

    Returns ``None`` on platforms that lack the POSIX ``resource`` module
    (Windows) so callers can safely use the result as
    ``preexec_fn=apply_subprocess_rlimits()`` without a platform check.
    """
    if sys.platform == "win32":
        return None

    # Imported here so the module imports cleanly on Windows for type checks /
    # CI; the inner function only runs on Unix where ``resource`` is available.
    import resource  # noqa: PLC0415 — POSIX-only import gated by platform check

    def _set_limits() -> None:
        # ``RLIMIT_AS`` is not honored on every Unix kernel (notably some
        # macOS releases ignore it for compressed memory accounting). Treat
        # all three calls as best-effort — better to start the subprocess
        # without a limit than to crash it before launch.
        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(resource.RLIMIT_AS, (address_space_bytes, address_space_bytes))

        with contextlib.suppress(AttributeError, ValueError, OSError):
            # ``RLIMIT_NPROC`` is absent on a few exotic Unix variants.
            resource.setrlimit(resource.RLIMIT_NPROC, (process_cap, process_cap))

        # Detach from the parent's process group so a runaway ``claude`` does
        # not propagate signals back to the FastAPI worker, and so we can
        # ``os.killpg`` the whole tree cleanly on timeout.
        with contextlib.suppress(OSError):
            os.setsid()

    return _set_limits
