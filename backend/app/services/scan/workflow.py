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

"""Workflow orchestrator for a scan run.

Walks the configured stage list, threading each stage's kept communities
into the next and emitting transitions to the supplied ``WorkflowObserver``
(typically ``DBTimelineObserver``, which lands them in
``scan_repo_runs`` / ``scan_repo_steps`` for the UI to poll). One run is
one async task; ``start_run`` returns immediately with a run id and the
actual work runs in the background.

Phase-chip transitions are batched per phase, not per stage. A phase may
roll up multiple sub-stages (``CODE_INDEX`` rolls up seven), and
each ``ScanRepoStep`` row is keyed on ``(run_id, phase)`` — so emitting
``on_step_running`` per sub-stage thrashes the row between RUNNING and
its terminal status seven times. We instead announce RUNNING once when
the first sub-stage of a phase starts, accumulate sub-stage detail
(see ``phase_accumulator.py``), and emit a single terminal observer call
when the next stage's phase differs (see ``phase_routing.py``).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from app.models.scan_phase import ScanPhase
from app.schemas.scan import (
    Community,
    RunConfig,
    TestRun,
)
from app.services.scan.observers import NoopObserver, WorkflowObserver
from app.services.scan.phase_accumulator import PhaseAccumulator
from app.services.scan.phase_routing import (
    flush_phase_failed,
    flush_phase_terminal,
    phase_for,
)
from app.services.scan.stages import StageContext, get_stage, known_stages

logger = structlog.get_logger(__name__)

# Hold strong references so background tasks don't get GC'd mid-run.
_RUNNING_TASKS: set[asyncio.Task[None]] = set()


async def start_run(
    *,
    repo_path: str,
    repo_name: str,
    config: RunConfig,
    observer: WorkflowObserver | None = None,
    runtime_overrides: dict[str, Any] | None = None,
    await_completion: bool = False,
) -> TestRun:
    """Build the in-memory run state and kick off the background task.

    ``observer`` is how transitions escape this function. ``scan_runner``
    passes a ``DBTimelineObserver`` so per-step rows land in
    ``scan_repo_runs`` / ``scan_repo_steps`` for the UI to poll; pass
    ``NoopObserver`` (the default) when callers don't need timeline
    output.

    ``runtime_overrides`` is a dict of values merged into every stage's
    config at execution time. ``scan_runner`` uses this to thread
    ``org_id`` / ``scan_id`` / ``repo_id`` etc. into wrapper
    stages that need a DB session, without rewriting ``RunConfig``.

    ``await_completion=True`` blocks until the run finishes — required
    by the multi-repo scan, whose caller must not advance to global
    phases / mark-scan-terminal until every per-repo stage (including
    the Claude synthesis subprocess) has returned.
    """
    run_id = uuid.uuid4().hex[:12]
    run = TestRun(
        run_id=run_id,
        repo_name=repo_name,
        repo_path=repo_path,
        config=config,
        status="queued",
        started_at=datetime.now(UTC),
    )

    coro = _execute_run(run, observer or NoopObserver(), runtime_overrides or {})
    if await_completion:
        await coro
        return run

    task = asyncio.create_task(coro)
    _RUNNING_TASKS.add(task)
    task.add_done_callback(_RUNNING_TASKS.discard)

    return run


async def _execute_run(
    run: TestRun, observer: WorkflowObserver, runtime_overrides: dict[str, Any]
) -> None:
    """Background body of one run. Streams progress through ``observer``."""
    run.status = "running"
    await observer.on_run_start()

    ctx = StageContext(
        run_id=run.run_id,
        repo_path=run.repo_path,
        repo_name=run.repo_name,
    )

    upstream: list[Community] = []
    cumulative_config: dict[str, Any] = dict(runtime_overrides)
    accumulators: dict[ScanPhase, PhaseAccumulator] = {}
    current_phase: ScanPhase | None = None

    try:
        for idx, stage_name in enumerate(run.config.stages):
            if stage_name not in known_stages():
                error = f"Unknown stage: {stage_name}"
                run.error = error
                if current_phase is not None:
                    await flush_phase_failed(observer, current_phase, accumulators, error)
                run.status = "failed"
                run.finished_at = datetime.now(UTC)
                await observer.on_run_failed(error=error)
                return

            stage_cfg = _stage_config(run.config, stage_name) | cumulative_config
            phase = phase_for(stage_name)

            if phase is not None and phase != current_phase:
                # Crossing into a new phase — announce RUNNING once.
                accumulators[phase] = PhaseAccumulator(
                    started_at=time.perf_counter(),
                    input_count=len(upstream),
                )
                current_phase = phase
                await observer.on_step_running(phase=phase, input_count=len(upstream))

            t0 = time.perf_counter()
            try:
                output = await get_stage(stage_name)(ctx, upstream, stage_cfg)
            except Exception as exc:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                logger.exception("scan_stage_failed", stage=stage_name, run=run.run_id)
                err_msg = f"{type(exc).__name__}: {exc}"[:500]
                run.status = "failed"
                run.finished_at = datetime.now(UTC)
                run.error = err_msg
                if phase is not None:
                    await flush_phase_failed(
                        observer, phase, accumulators, err_msg, duration_ms=duration_ms
                    )
                await observer.on_run_failed(error=err_msg)
                return

            duration_ms = int((time.perf_counter() - t0) * 1000)
            kept = len(output.communities)
            dropped = len(output.dropped)
            stage_input = _extras_count(output.extras, "input_count", len(upstream))
            stage_kept = _extras_count(output.extras, "kept_count", kept)
            stage_dropped = _extras_count(output.extras, "dropped_count", dropped)
            is_skipped = bool(
                output.extras.get("skipped_unchanged") or output.extras.get("skipped_cache")
            )

            if phase is not None:
                # Override the per-stage input_count with the fold-friendly
                # value so the popover roll-up renders the reduction story.
                stage_extras_for_acc = dict(output.extras)
                stage_extras_for_acc["input_count"] = stage_input
                accumulators[phase].record(
                    stage_name=stage_name,
                    is_skipped=is_skipped,
                    kept=stage_kept,
                    dropped=stage_dropped,
                    duration_ms=duration_ms,
                    stage_extras=stage_extras_for_acc,
                )

            # Stage 0's ``worktree_path`` flows into Stage 1's cypher cwd.
            # When ingest skips via the cache predicate, propagate the
            # decision so reduction stages short-circuit with consistent
            # metadata (head_sha + reason in their extras too).
            #
            # ``ingest_head_sha`` is propagated WHENEVER ingest produces
            # one — not just on the skip path — because ``extract`` keys
            # its Postgres community cache on ``(repo_id, head_sha)`` and
            # needs the SHA in cumulative config even when ingest ran
            # gitnexus-analyze afresh (e.g. synth-skip predicate forced
            # the reduction chain to re-run).
            if stage_name == "ingest":
                cumulative_config["ingest_skipped"] = bool(output.extras.get("skipped_unchanged"))
                if output.extras.get("skipped_unchanged"):
                    cumulative_config["ingest_skip_reason"] = output.extras.get("skipped_reason")
                head_sha = output.extras.get("head_sha")
                if head_sha:
                    cumulative_config["ingest_head_sha"] = head_sha
                if "worktree_path" in output.extras:
                    cumulative_config["ingest_worktree_path"] = output.extras["worktree_path"]

            upstream = output.communities

            # Phase-boundary check: peek the next stage. If its phase
            # differs (or there is no next stage), flush the terminal
            # observer call for the phase we just completed.
            next_stage_name = (
                run.config.stages[idx + 1] if idx + 1 < len(run.config.stages) else None
            )
            next_phase = phase_for(next_stage_name) if next_stage_name else None
            if phase is not None and next_phase != phase:
                await flush_phase_terminal(observer, phase, accumulators)
                current_phase = None

        run.status = "done"
        run.finished_at = datetime.now(UTC)
        await observer.on_run_done()
    except asyncio.CancelledError:
        # Cancellation (process shutdown / dev-server reload) bypasses
        # ``except Exception`` — it's a ``BaseException``. Stamp the
        # ``scan_repo_runs`` row terminal before re-raising so the UI's
        # scan-active check doesn't get stuck on a perpetual RUNNING
        # row.
        logger.warning("scan_run_cancelled", run=run.run_id)
        run.status = "failed"
        run.error = "Worker cancelled before completion"
        run.finished_at = datetime.now(UTC)
        if current_phase is not None:
            await flush_phase_failed(observer, current_phase, accumulators, run.error)
        await observer.on_run_failed(error=run.error)
        raise
    except Exception as exc:
        logger.exception("scan_run_failed", run=run.run_id)
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"[:500]
        run.finished_at = datetime.now(UTC)
        if current_phase is not None:
            await flush_phase_failed(observer, current_phase, accumulators, run.error)
        await observer.on_run_failed(error=run.error or "")


def _stage_config(config: RunConfig, name: str) -> dict[str, Any]:
    """Pull the per-stage config dict off the run config, defaulting to ``{}``."""
    return getattr(config, name, {}) or {}


def _extras_count(extras: dict[str, Any], key: str, default: int) -> int:
    """Read an int count override from ``extras``, falling back to ``default``.

    Stages that compute their reduction independently of
    ``StageOutput.communities`` / ``StageOutput.dropped`` (e.g. synthesis,
    where the real output is per-feature DB rows) populate counts
    under these well-known keys. Non-int values fall back so a stale
    schema doesn't crash the pipeline.
    """
    value = extras.get(key)
    return int(value) if isinstance(value, int) else default
