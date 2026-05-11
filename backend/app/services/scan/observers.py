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

"""Workflow observer protocol — pluggable transition callbacks.

The workflow body in ``workflow.py`` runs every stage and emits status
transitions. Sandbox runs persist via JSON-on-disk only; multi-repo
scans want the same transitions written into ``scan_repo_runs`` +
``scan_repo_steps`` so the timeline UI can read them in real time.

Two implementations:

* :class:`NoopObserver` — does nothing. Used by the legacy single-repo
  sandbox runs to preserve existing behaviour.
* :class:`DBTimelineObserver` — writes every transition into the
  scan_repo_runs / scan_repo_steps tables. Lives in the sibling
  ``db_timeline_observer`` module to keep this file under the
  per-file LOC budget.

The Protocol lets us add SSE event-bus publishing or other sinks later
without touching the workflow body.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.models.scan_phase import ScanPhase
from app.services.scan.db_timeline_observer import DBTimelineObserver


class WorkflowObserver(Protocol):
    """Hook surface called by the workflow at every transition.

    All methods are async because DB-backed observers need a session.
    All methods are no-throw — observer failures must not abort the
    pipeline. Implementations log and swallow.
    """

    async def on_run_start(self) -> None: ...

    async def on_step_running(self, *, phase: ScanPhase, input_count: int) -> None: ...

    async def on_step_done(
        self,
        *,
        phase: ScanPhase,
        input_count: int,
        kept_count: int,
        dropped_count: int,
        duration_ms: int,
        extras: dict[str, Any],
    ) -> None: ...

    async def on_step_failed(self, *, phase: ScanPhase, error: str, duration_ms: int) -> None: ...

    async def on_step_skipped_cache(self, *, phase: ScanPhase, extras: dict[str, Any]) -> None: ...

    async def on_run_done(self, *, feature_count: int | None = None) -> None: ...

    async def on_run_failed(self, *, error: str) -> None: ...


class NoopObserver:
    """No-op observer for sandbox runs that only persist via JSON-on-disk."""

    async def on_run_start(self) -> None:
        return None

    async def on_step_running(self, *, phase: ScanPhase, input_count: int) -> None:
        return None

    async def on_step_done(
        self,
        *,
        phase: ScanPhase,
        input_count: int,
        kept_count: int,
        dropped_count: int,
        duration_ms: int,
        extras: dict[str, Any],
    ) -> None:
        return None

    async def on_step_failed(self, *, phase: ScanPhase, error: str, duration_ms: int) -> None:
        return None

    async def on_step_skipped_cache(self, *, phase: ScanPhase, extras: dict[str, Any]) -> None:
        return None

    async def on_run_done(self, *, feature_count: int | None = None) -> None:
        return None

    async def on_run_failed(self, *, error: str) -> None:
        return None


__all__ = ["DBTimelineObserver", "NoopObserver", "WorkflowObserver"]
