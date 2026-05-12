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

"""Wrap the ``claude`` argv with ``sandbox-exec`` on macOS Hybrid mode.

Phase E — Layer 7. Opt-in via ``BODHIORCHARD_HYBRID_SANDBOX=1``. When
enabled and running on Darwin, ``maybe_wrap_with_sandbox()`` prepends
``sandbox-exec -f bodhi.sb -D WORKSPACE=... -D HOME_DIR=... ...`` to
the command list before ``asyncio.create_subprocess_exec`` is called.

On Linux / Windows or when the env flag is unset, returns the cmd
unchanged. The wrapping is intentionally side-effect-free so it can
be slotted in at any spawn site without changing the rest of the
flow.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_PROFILE_PATH = str(Path(__file__).resolve().parent / "bodhi.sb")


def _is_enabled() -> bool:
    """The sandbox wraps when both gates are satisfied."""
    if sys.platform != "darwin":
        return False
    if os.environ.get("BODHIORCHARD_HYBRID_SANDBOX", "0") != "1":
        return False
    return shutil.which("sandbox-exec") is not None


def maybe_wrap_with_sandbox(cmd: list[str], cwd: str) -> list[str]:
    """Return a possibly-wrapped argv. No-op unless macOS + env flag.

    The Seatbelt profile takes four parameters which we pass via
    ``-D KEY=VALUE``. If the user's ``HOME`` or ``TMPDIR`` is unset
    (unusual but possible inside test runners), we fall back to safe
    defaults instead of crashing.
    """
    if not _is_enabled():
        return cmd

    home = os.environ.get("HOME") or os.path.expanduser("~")
    tmpdir = os.environ.get("TMPDIR") or "/tmp"
    python_bin = sys.executable

    return [
        "sandbox-exec",
        "-f",
        _PROFILE_PATH,
        "-D",
        f"WORKSPACE={cwd}",
        "-D",
        f"HOME_DIR={home}",
        "-D",
        f"TMPDIR={tmpdir}",
        "-D",
        f"PYTHON_BIN={python_bin}",
        *cmd,
    ]
