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

"""In-memory tool-use counter for an in-flight synthesis run.

The synthesise stage's ``progress_callback`` invokes :func:`record`
on every Claude tool_use block in the stream. The scan-status
serializer peeks the counters at poll time and folds them into the
``feature_synthesis`` step's ``extras`` so the chip popover surfaces
"model has called Read 3 times, write_synthesis_feature 1 time"
*before* any feature has actually been written.

Why a separate module from :mod:`app.mcp.synthesis_accumulator`:

* The accumulator buffers persisted artefacts (what gets reconciled
  at end-of-batch). This module tracks ephemeral activity (reads /
  internal MCP tool calls) that has no DB row to land on.
* They have different lifecycle hooks — the accumulator is drained
  on success; progress counters are reset on every new run (success
  or failure) so the next scan starts at zero.

Pre-prod local-dev: a process-level dict is plenty. Future scale-out
can swap the backing store for Redis without touching callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class ToolProgress:
    """Per-(org_id, repo_id) counter snapshot."""

    total: int = 0
    by_tool: dict[str, int] = field(default_factory=dict)
    last_tool: str | None = None
    last_at: str | None = None


_progress: dict[str, ToolProgress] = {}


def _key(org_id: str, *, repo_id: str) -> str:
    """Build the progress key. Mirrors the accumulator's keying convention
    so a future Redis migration can share the same hash slot."""
    return f"{org_id}:{repo_id}"


def record(org_id: str, repo_id: str, tool_name: str) -> None:
    """Increment counters for one tool_use block."""
    snap = _progress.setdefault(_key(org_id, repo_id=repo_id), ToolProgress())
    snap.total += 1
    snap.by_tool[tool_name] = snap.by_tool.get(tool_name, 0) + 1
    snap.last_tool = tool_name
    snap.last_at = datetime.now(UTC).isoformat()


def peek(org_id: str, repo_id: str) -> dict[str, object] | None:
    """Snapshot the counter without resetting it. Returns ``None`` when
    no tool-uses have been recorded yet so the serializer can omit the
    extras keys cleanly rather than render a misleading ``0 calls``."""
    snap = _progress.get(_key(org_id, repo_id=repo_id))
    if snap is None or snap.total == 0:
        return None
    return {
        "total": snap.total,
        "by_tool": dict(snap.by_tool),
        "last_tool": snap.last_tool,
        "last_at": snap.last_at,
    }


def reset(org_id: str, repo_id: str) -> None:
    """Drop the counter for ``(org_id, repo_id)``. Called at the start
    of every synthesis run so a re-scan doesn't accumulate counts from
    the previous attempt."""
    _progress.pop(_key(org_id, repo_id=repo_id), None)


def reset_for_org(org_id: str) -> None:
    """Drop every counter for an org. Used by scan-cancel / failure paths
    in lockstep with :func:`app.mcp.synthesis_accumulator.reset_for_org`."""
    prefix = f"{org_id}:"
    for key in [k for k in _progress if k.startswith(prefix)]:
        _progress.pop(key, None)
