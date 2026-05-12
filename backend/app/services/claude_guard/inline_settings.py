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

"""Inline ``--settings`` JSON for the ``claude`` subprocess.

The CLI accepts ``--settings <inline-json>`` to override the user's
``~/.claude/settings.json`` for that invocation only. We use the flag for
three things:

* ``outputStyle: "default"`` — neutralizes a developer's interactive
  outputStyle (e.g. ``learning``) that would inject ``★ Insight`` blocks
  into skill output (see ``project_claude_subprocess_isolation`` memory).
* ``permissions.deny`` — the Phase B inline deny list, evaluated by
  Claude's prefix matcher before any tool runs. Bypassable, but cheap.
* ``hooks.PreToolUse`` — invokes ``pretool_guard.py`` for every Bash /
  Read / Edit / Write event, the real gate.

Because the value is passed via the CLI flag, a malicious
``.claude/settings.json`` planted in a scanned repo cannot override us
(CVE-2026-25725 class).
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from typing import Any

from app.services.claude_guard.deny_rules import INLINE_DENY_LIST

_HOOK_SCRIPT = str(Path(__file__).resolve().parent / "pretool_guard.py")


def build_inline_settings_json() -> str:
    """Return the JSON string to hand to ``claude --settings``.

    The hook command uses the parent process's ``sys.executable`` so the
    subprocess inherits the same interpreter — important under Hybrid
    mode where the conda env's Python differs from system Python.
    Both halves are ``shlex.quote``-d so a Python install path that
    contains spaces (``/Applications/Python 3.12/...``) still produces
    a well-formed shell command.
    """
    hook_command = f"{shlex.quote(sys.executable)} {shlex.quote(_HOOK_SCRIPT)}"
    payload: dict[str, Any] = {
        "outputStyle": "default",
        "permissions": {
            "deny": INLINE_DENY_LIST,
            # Hard-disable bypassPermissions inside the subprocess so a
            # planted ``.claude/settings.json`` cannot re-enable YOLO mode.
            "disableBypassPermissionsMode": "disable",
        },
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": hook_command}],
                },
                {
                    "matcher": "Read|Edit|Write",
                    "hooks": [{"type": "command", "command": hook_command}],
                },
            ],
        },
    }
    return json.dumps(payload)
