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
* ``permissions.deny`` — the inline deny list, evaluated by Claude's
  prefix matcher before any tool runs. Bypassable, but cheap.
* ``hooks.PreToolUse`` / ``hooks.PostToolUse`` — invoke the guard
  scripts on Bash / Read / Edit / Write events; the real gate plus the
  audit-log writer.

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

_PRE_HOOK_SCRIPT = str(Path(__file__).resolve().parent / "pretool_guard.py")
_POST_HOOK_SCRIPT = str(Path(__file__).resolve().parent / "posttool_guard.py")


def build_inline_settings_json() -> str:
    """Return the JSON string to hand to ``claude --settings``.

    The hook command uses the parent process's ``sys.executable`` so the
    subprocess inherits the same interpreter — important under Hybrid
    mode where the conda env's Python differs from system Python.
    Both halves are ``shlex.quote``-d so a Python install path that
    contains spaces (``/Applications/Python 3.12/...``) still produces
    a well-formed shell command.
    """
    py = shlex.quote(sys.executable)
    pre_hook = f"{py} {shlex.quote(_PRE_HOOK_SCRIPT)}"
    post_hook = f"{py} {shlex.quote(_POST_HOOK_SCRIPT)}"
    payload: dict[str, Any] = {
        "outputStyle": "default",
        "permissions": {
            "deny": INLINE_DENY_LIST,
            # NOTE: ``disableBypassPermissionsMode`` is intentionally NOT
            # set. When combined with ``--dangerously-skip-permissions``
            # it forces the subprocess into normal permission mode where
            # every MCP tool needs an explicit allow rule — and we have
            # none, so every ``mcp__bodhiorchard__write_bud`` call gets
            # denied. The PM agent reported this as "write_bud /
            # get_bud_context MCP tools are not available in this
            # session" and emitted markdown without persisting.
            #
            # Defense against planted ``.claude/settings.json`` files
            # re-enabling YOLO still holds because:
            # (a) the inline ``--settings`` flag passed here takes
            #     precedence over any repo-local ``.claude/settings.json``;
            # (b) the deny list above still applies regardless of mode;
            # (c) the PreToolUse hook gates Bash / Read / Edit / Write
            #     regardless of the permission-mode toggle.
        },
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": pre_hook}],
                },
                {
                    "matcher": "Read|Edit|Write",
                    "hooks": [{"type": "command", "command": pre_hook}],
                },
            ],
            # Audit observability: append every completed tool call to
            # the audit JSONL so we can later promote real usage into
            # per-skill tool budgets (per-skill tool budgets deferred).
            "PostToolUse": [
                {
                    "matcher": "Bash|Read|Edit|Write|Glob|Grep",
                    "hooks": [{"type": "command", "command": post_hook}],
                },
            ],
        },
    }
    return json.dumps(payload)
