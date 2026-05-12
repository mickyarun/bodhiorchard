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

"""PostToolUse hook — audits every successful tool call.

Companion to ``pretool_guard``. Where the pre-hook denies, this
post-hook just observes: on every tool completion (success or failure),
appends one record to the audit JSONL so we can later answer "what did
this skill actually do?" or "which deny rule fires most often in
production?".

Never modifies the result; always returns exit 0.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _THIS_DIR.parent.parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.claude_guard.audit_log import (  # noqa: E402 — sys.path mutation above
    append_event,
)


def main() -> int:
    """Read PostToolUse event JSON on stdin, append to audit log, exit 0."""
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
        tool_name = event.get("tool_name", "")
        tool_input = event.get("tool_input") or {}
        # Anthropic's PostToolUse payload includes ``tool_response``
        # with a status code / error message. We treat presence of
        # ``error`` as a failure for the audit decision.
        tool_response = event.get("tool_response") or {}
        decision = "failed" if tool_response.get("error") else "completed"

        append_event(
            event="post_tool",
            tool_name=tool_name,
            decision=decision,
            tool_input=tool_input,
            reason=tool_response.get("error"),
        )
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        # Audit must never brick the subprocess.
        print(f"posttool_guard: error, skipping audit: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
