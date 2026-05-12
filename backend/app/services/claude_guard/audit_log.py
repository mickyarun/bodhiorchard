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

"""Append-only audit log for Claude subprocess tool decisions.

Every PreToolUse / PostToolUse hook invocation appends one JSON record
to a configurable path (``BODHIORCHARD_AUDIT_LOG`` env var, default
``~/.bodhiorchard/security_events.jsonl``). Records are line-delimited
JSON so the file is grep-able and replay-able into the DB without a
parser.

Schema:

    {
      "ts": "2026-05-13T01:23:45.678Z",
      "event": "pre_tool" | "post_tool",
      "tool_name": "Bash" | "Read" | ...,
      "decision": "allow" | "deny" | "completed" | "failed",
      "rule": null | "env_exfil" | "network_exfil" | ...,
      "reason": null | "...",
      "tool_input_preview": "first 200 chars",
      "cwd": "...",                # PreToolUse only
      "duration_ms": 123,           # PostToolUse only
      "session": null | "<id>",     # if BODHIORCHARD_AGENT_SESSION is set
      "skill": null | "designer"    # if BODHIORCHARD_AGENT_SKILL_SLUG is set
    }

The log is opened with ``O_APPEND`` so concurrent hook invocations from
parallel ``claude`` subprocesses don't clobber each other. Failures are
swallowed — the audit log is observability, not a hard dependency, and
must never brick the subprocess.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

_DEFAULT_LOG_PATH = "~/.bodhiorchard/security_events.jsonl"
# Cap a single line at 8 KiB to avoid runaway lines if a tool_input is
# enormous (e.g. a 1 MB file Edit). Truncation is announced via a marker.
_LINE_BYTE_CAP = 8 * 1024
_PREVIEW_CHAR_CAP = 200


def _log_path() -> Path:
    raw = os.environ.get("BODHIORCHARD_AUDIT_LOG", _DEFAULT_LOG_PATH)
    return Path(raw).expanduser()


def _preview(value: object) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text[:_PREVIEW_CHAR_CAP] + ("…" if len(text) > _PREVIEW_CHAR_CAP else "")


def append_event(
    event: str,
    tool_name: str,
    decision: str,
    *,
    rule: str | None = None,
    reason: str | None = None,
    tool_input: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> None:
    """Append one decision record. Never raises — swallows every error."""
    record: dict[str, Any] = {
        "ts": dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds"),
        "event": event,
        "tool_name": tool_name,
        "decision": decision,
        "rule": rule,
        "reason": reason,
        "tool_input_preview": _preview((tool_input or {}).get("command") or tool_input),
        "cwd": os.environ.get("PWD"),
        "duration_ms": duration_ms,
        "session": os.environ.get("BODHIORCHARD_AGENT_SESSION"),
        "skill": os.environ.get("BODHIORCHARD_AGENT_SKILL_SLUG"),
    }
    line = json.dumps(record, default=str)
    if len(line.encode("utf-8")) > _LINE_BYTE_CAP:
        # Truncate the preview and retry — at this point the line is
        # bounded by the other fixed-size fields.
        record["tool_input_preview"] = record["tool_input_preview"][:512] + "…[truncated]"
        line = json.dumps(record, default=str)

    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Open with O_APPEND so concurrent writers don't overlap. Each
        # ``write`` of a complete line is atomic on POSIX up to PIPE_BUF
        # (4 KiB), which our cap above respects.
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        fd = os.open(str(path), flags, 0o600)
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    except OSError:
        # Audit failures must never propagate.
        return
