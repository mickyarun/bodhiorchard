# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Maps workflow stage names to ``ScanPhase`` enum values + phase-flush helpers.

Multiple reduction stages (e.g. ``ingest``, ``extract``, ``merge_labels``,
``filter_infra``, ``hierarchical``, ``size_floor``, ``top_n``) all roll
up under a single phase (``CODE_INDEX``). The workflow announces
that phase RUNNING when the first sub-stage starts and emits exactly
one terminal call when the phase boundary is crossed; this module owns
the mapping and the flush helpers.
"""

from __future__ import annotations

import time

from app.models.scan_phase import ScanPhase
from app.services.scan.observers import WorkflowObserver
from app.services.scan.phase_accumulator import PhaseAccumulator

# Map the workflow's stage_name strings → ``ScanPhase`` enum values.
# All seven reduction stages roll up under ``CODE_INDEX``. The
# per-repo skill / design-system stages map to their own phases.
STAGE_TO_PHASE: dict[str, ScanPhase] = {
    "repo_setup": ScanPhase.REPO_SETUP,
    "ingest": ScanPhase.CODE_INDEX,
    "extract": ScanPhase.CODE_INDEX,
    "merge_labels": ScanPhase.CODE_INDEX,
    "filter_infra": ScanPhase.CODE_INDEX,
    "hierarchical": ScanPhase.CODE_INDEX,
    "size_floor": ScanPhase.CODE_INDEX,
    "top_n": ScanPhase.CODE_INDEX,
    "synthesize": ScanPhase.FEATURE_SYNTHESIS,
    "skill_extraction": ScanPhase.SKILL_EXTRACTION,
    "design_system": ScanPhase.DESIGN_SYSTEM_EXTRACT,
    "skill_remap": ScanPhase.SKILL_REMAP,
    "feature_merge": ScanPhase.FEATURE_MERGE,
    "persist_results": ScanPhase.PERSIST_RESULTS,
}


def phase_for(stage_name: str) -> ScanPhase | None:
    """Look up the ``ScanPhase`` this workflow stage rolls up to, if any."""
    return STAGE_TO_PHASE.get(stage_name)


async def flush_phase_terminal(
    observer: WorkflowObserver,
    phase: ScanPhase,
    accumulators: dict[ScanPhase, PhaseAccumulator],
) -> None:
    """Emit one terminal observer call for ``phase``.

    Skipped-cache iff every sub-stage in the phase short-circuited;
    otherwise done. The chip's ``duration_ms`` reflects the elapsed
    time across all sub-stages, not just the last one.
    """
    acc = accumulators.get(phase)
    if acc is None:
        return
    duration_ms = int((time.perf_counter() - acc.started_at) * 1000)
    extras = acc.terminal_extras()
    if acc.all_skipped:
        await observer.on_step_skipped_cache(phase=phase, extras=extras)
    else:
        await observer.on_step_done(
            phase=phase,
            input_count=acc.input_count,
            kept_count=acc.kept_count,
            dropped_count=acc.dropped_count,
            duration_ms=duration_ms,
            extras=extras,
        )


async def flush_phase_failed(
    observer: WorkflowObserver,
    phase: ScanPhase,
    accumulators: dict[ScanPhase, PhaseAccumulator],
    error: str,
    *,
    duration_ms: int | None = None,
) -> None:
    """Emit a single ``on_step_failed`` for the phase that was running.

    Rolls up the accumulated sub-stage trail into the failure extras so
    the popover preserves what ran successfully before the throw. If the
    accumulator was never populated (e.g., the very first stage threw),
    falls back to a minimal failure record.
    """
    acc = accumulators.get(phase)
    duration = duration_ms
    if acc is not None:
        duration = duration_ms or int((time.perf_counter() - acc.started_at) * 1000)
    await observer.on_step_failed(
        phase=phase,
        error=error,
        duration_ms=duration or 0,
    )
