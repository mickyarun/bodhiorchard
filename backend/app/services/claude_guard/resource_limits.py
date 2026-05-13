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
subprocess that allocates 64 GiB of RAM before the timeout fires
(classic crypto-miner pattern seen in prompt-injection incidents). This
module returns a ``preexec_fn`` callable that runs between ``fork`` and
``exec`` and applies ``RLIMIT_AS`` to cap that.

Caveat on ``RLIMIT_NPROC`` — read before tuning
------------------------------------------------
The Linux/macOS ``RLIMIT_NPROC`` rlimit is **per-user**, not per-
subprocess-tree. The kernel counts the calling user's *total* process
count against this cap, including unrelated apps (Claude Desktop
helpers, Chrome renderers, Slack, Docker, etc.). On a developer
workstation that count sits at 600–1500 easily, and a tight cap blows
up the first ``fork()`` our subprocess attempts (e.g. spawning the MCP
stdio bridge), with no diagnostic that points at the rlimit — the
subprocess silently fails to register MCP tools and the agent reports
them as "not available".

The cap here is therefore set high enough that legitimate dev hosts
never trip it; it is **not** an effective fork-bomb defense. The real
bound on runaway behavior is ``timeout_seconds``. Genuine per-tree
process containment requires one of:

  * cgroups v2 (Linux only) via ``systemd-run --user --scope --slice=...``
  * macOS ``launchctl limit`` quotas in a dedicated session
  * Running the subprocess as a separate UID under a low-NPROC user

None of those are wired in here; they belong in the deployment layer
(Layer 6 firewall + container limits / Layer 7 Seatbelt profile).

``setsid`` IS the load-bearing call in this preexec — it gives the
parent a clean ``killpg`` target so timeout enforcement actually
terminates the whole subprocess tree instead of leaking workers.
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

# Per-USER process cap. The kernel counts the CALLING USER's TOTAL process
# count against this limit, not just the subprocess tree we control. On a
# dev workstation with Claude Desktop, Chrome, Slack, Docker etc. the user
# easily sits at 600+ processes — a tight cap blows up the very first
# ``fork()`` the ``claude`` child needs (e.g. to spawn the MCP bridge), and
# the subprocess silently fails to start its MCP server. Set high enough
# that legitimate developer workstations don't trip; the wall-clock
# ``timeout_seconds`` knob is the real bound on runaway behavior.
_DEFAULT_PROCESS_CAP: int = 16384


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
