#!/usr/bin/env python3
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

"""PreToolUse hook — the real Bash / Read gate for ``claude`` subprocesses.

This script is registered in the inline ``--settings`` JSON that
``claude_runner`` passes to the CLI. The CLI invokes it for every
PreToolUse event, feeds the tool call as JSON on stdin, and treats stdout
as the decision response.

Behavior per Anthropic's hook contract
(https://code.claude.com/docs/en/hooks):

* Read JSON ``{"tool_name": str, "tool_input": {...}}`` from stdin.
* If the tool is a Bash command matching one of our regex rules, or a
  Read/Edit on a canonicalized path matching the secret-file rules,
  emit a ``permissionDecision: "deny"`` JSON response on stdout.
* On any unexpected error, allow the call through and log to stderr —
  failing closed would brick the subprocess if the hook script itself
  has a bug, so we fail open and rely on the inline ``permissions.deny``
  layer as a backstop.

Runs as a standalone script (``python3 pretool_guard.py``) — no backend
dependencies, no DB access, sub-100ms latency.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Allow this script to import ``app.services.claude_guard.deny_rules`` when
# invoked directly as a subprocess hook. ``Path(__file__).parent`` is the
# ``claude_guard`` package dir; walking up three levels lands on the
# ``backend/`` repo root, which is what makes ``app.services...`` importable.
_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _THIS_DIR.parent.parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.claude_guard.audit_log import append_event  # noqa: E402 — sys.path
from app.services.claude_guard.deny_rules import (  # noqa: E402 — sys.path mutation above
    match_bash_deny,
    match_path_deny,
)


def _deny(reason: str) -> dict[str, Any]:
    """Build the JSON deny response per Anthropic's hook contract."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _canonical_path(raw: str) -> str:
    """Resolve symlinks + ``..`` so we match the real target.

    Defeats the CVE-2026-39861 class where an attacker plants a symlink
    inside the workspace pointing at ``/etc/passwd`` and then reads it
    via the workspace path. ``realpath`` follows the symlink so the
    deny rules see the real target.
    """
    try:
        return os.path.realpath(os.path.expanduser(raw))
    except (OSError, ValueError):
        return raw


def evaluate(event: dict[str, Any]) -> dict[str, Any] | None:
    """Decide on a tool call. Return deny JSON or ``None`` to allow."""
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}

    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        hit = match_bash_deny(command)
        if hit:
            rule_name, matched = hit
            return _deny(
                f"Blocked by Phase B Bash deny rule '{rule_name}' "
                f"(matched substring: {matched!r}). "
                "If this is a legitimate command, contact the operator."
            )

    elif tool_name in ("Read", "Edit", "Write"):
        path = str(tool_input.get("file_path") or tool_input.get("path") or "")
        if not path:
            return None
        canonical = _canonical_path(path)
        # Match the canonical path (so symlink escapes are caught) but
        # also the raw to catch ``~/.ssh/x`` style references that
        # ``expanduser`` would only resolve on a host with the matching
        # user — defense in depth.
        hit = match_path_deny(canonical) or match_path_deny(path)
        if hit:
            rule_name, matched = hit
            return _deny(
                f"Blocked by Phase B path deny rule '{rule_name}' "
                f"(matched substring: {matched!r}). "
                f"Resolved path: {canonical!r}"
            )

    return None


def main() -> int:
    """Read stdin, decide, write stdout. Always exit 0 (fail open on error).

    Every decision (allow or deny) is also appended to the audit JSONL so
    Phase F observability captures the full tool-call stream.
    """
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
        decision = evaluate(event)
        tool_name = event.get("tool_name", "")
        tool_input = event.get("tool_input") or {}

        if decision is not None:
            reason_text = decision["hookSpecificOutput"].get("permissionDecisionReason", "")
            # Extract the rule name out of the standardized reason text
            # for cleaner audit grouping. Falls back to ``"unknown"``.
            rule = "unknown"
            if "rule '" in reason_text:
                rule = reason_text.split("rule '", 1)[1].split("'", 1)[0]

            append_event(
                event="pre_tool",
                tool_name=tool_name,
                decision="deny",
                rule=rule,
                reason=reason_text,
                tool_input=tool_input,
            )
            json.dump(decision, sys.stdout)
            sys.stdout.write("\n")
        else:
            append_event(
                event="pre_tool",
                tool_name=tool_name,
                decision="allow",
                tool_input=tool_input,
            )
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        # Fail open: a buggy hook should not brick the subprocess. The
        # inline ``permissions.deny`` layer remains as backstop.
        print(f"pretool_guard: error, allowing: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
