# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Unit tests for the legacy ScanStatusData adapter.

Exercises the pure-function helpers in ``services/scan/serialize.py``
that derive the legacy progress / phase shape from scan ORM rows. The
``build_legacy_status`` integration is exercised indirectly via
``test_feature_merge.py`` and the e2e SetupChecklist polling — these
tests guard the maths and the enum-coverage invariants.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.models.scan_phase import ScanPhase
from app.models.scan_run_enums import RepoRunStatus, StepStatus
from app.services.scan.serialize import (
    _PHASE_LABELS,
    _collect_warnings,
    _compute_progress,
    _legacy_status,
    _render_phase_rows,
)

# --- stubs ------------------------------------------------------------


@dataclass
class _StubRun:
    """Minimal ScanRepoRun-shaped stub for the pure-function tests."""

    id: uuid.UUID
    repo_id: uuid.UUID
    status: RepoRunStatus
    error: str | None = None


@dataclass
class _StubStep:
    """Minimal ScanRepoStep-shaped stub."""

    phase: ScanPhase
    status: StepStatus
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


def _run(status: RepoRunStatus = RepoRunStatus.RUNNING) -> _StubRun:
    return _StubRun(id=uuid.uuid4(), repo_id=uuid.uuid4(), status=status)


def _step(
    phase: ScanPhase,
    status: StepStatus = StepStatus.DONE,
) -> _StubStep:
    return _StubStep(phase=phase, status=status)


# --- _compute_progress -----------------------------------------------


def test_compute_progress_returns_zero_for_no_runs() -> None:
    """Edge case: no runs → 0%, never NaN / division-by-zero."""
    assert _compute_progress([], {}) == 0.0


def test_compute_progress_zero_when_nothing_terminal() -> None:
    """Single repo, no terminal steps → 0%."""
    run = _run()
    steps_by_run = {run.id: [_step(ScanPhase.REPO_SETUP, StepStatus.RUNNING)]}
    assert _compute_progress([run], steps_by_run) == 0.0


def test_compute_progress_partial_under_100() -> None:
    """One DONE step out of expected 11 (8 per-repo + 3 global) ≈ 9%."""
    run = _run()
    steps_by_run = {run.id: [_step(ScanPhase.REPO_SETUP, StepStatus.DONE)]}
    result = _compute_progress([run], steps_by_run)
    assert 5.0 < result < 12.0


def test_compute_progress_all_done_caps_at_100() -> None:
    """All 8 per-repo + 4 global terminals → exactly 100%."""
    run = _run(RepoRunStatus.DONE)
    steps_by_run = {
        run.id: [
            _step(ScanPhase.MODE_DETECTION, StepStatus.DONE),
            _step(ScanPhase.REPO_SETUP, StepStatus.DONE),
            _step(ScanPhase.CODE_INDEX, StepStatus.DONE),
            _step(ScanPhase.STALE_CLEANUP, StepStatus.DONE),
            _step(ScanPhase.SKILL_EXTRACTION, StepStatus.DONE),
            _step(ScanPhase.DESIGN_SYSTEM_EXTRACT, StepStatus.DONE),
            _step(ScanPhase.FEATURE_SYNTHESIS, StepStatus.DONE),
            _step(ScanPhase.EXTRACT_ROUTES, StepStatus.DONE),
            _step(ScanPhase.SKILL_REMAP, StepStatus.DONE),
            _step(ScanPhase.BACKEND_LINK, StepStatus.DONE),
            _step(ScanPhase.EMBEDDING_BACKFILL, StepStatus.DONE),
            _step(ScanPhase.PERSIST_RESULTS, StepStatus.DONE),
        ]
    }
    assert _compute_progress([run], steps_by_run) == 100.0


def test_compute_progress_resume_does_not_double_count_phase() -> None:
    """A repo whose phase has both a prior-pass DONE step *and* a
    fresh RUNNING step counts the phase exactly once.

    Naive step-counting would put us at 2/11 ≈ 18% on a single phase;
    distinct-pair counting keeps it at 1/11 ≈ 9% — the value that
    correctly reflects one phase reaching terminal.
    """
    run = _run()
    steps_by_run = {
        run.id: [
            # Old DONE step from the prior pass (not yet cleared).
            _step(ScanPhase.REPO_SETUP, StepStatus.DONE),
            # New RUNNING step from the resumed walk.
            _step(ScanPhase.REPO_SETUP, StepStatus.RUNNING),
        ]
    }
    result = _compute_progress([run], steps_by_run)
    # One unique terminal pair → 1/11 of the budget.
    assert 5.0 < result < 12.0


def test_compute_progress_skipped_cache_counts_as_terminal() -> None:
    """SKIPPED_CACHE is a valid terminal — the work was reused, not skipped over."""
    run = _run()
    steps_by_run = {run.id: [_step(ScanPhase.CODE_INDEX, StepStatus.SKIPPED_CACHE)]}
    assert _compute_progress([run], steps_by_run) > 0.0


# --- _PHASE_LABELS coverage ------------------------------------------


def test_phase_labels_cover_every_pipeline_phase() -> None:
    """Each ScanPhase value used by the pipeline must have a UI label.

    Excludes meta-phase enum values (PER_REPO / GLOBAL / status &
    error-code variants) which are not phase rows.
    """
    pipeline_phases = {
        ScanPhase.MODE_DETECTION,
        ScanPhase.CODE_INDEX,
        ScanPhase.REPO_SETUP,
        ScanPhase.STALE_CLEANUP,
        ScanPhase.SKILL_EXTRACTION,
        ScanPhase.DESIGN_SYSTEM_EXTRACT,
        ScanPhase.FEATURE_SYNTHESIS,
        ScanPhase.EXTRACT_ROUTES,
        ScanPhase.SKILL_REMAP,
        ScanPhase.BACKEND_LINK,
        ScanPhase.EMBEDDING_BACKFILL,
        ScanPhase.PERSIST_RESULTS,
    }
    missing = pipeline_phases - set(_PHASE_LABELS.keys())
    assert not missing, f"_PHASE_LABELS missing entries for: {sorted(p.value for p in missing)}"


# --- _legacy_status ---------------------------------------------------


def test_legacy_status_maps_to_three_buckets() -> None:
    """Frontend only understands running / completed / failed."""
    assert _legacy_status("completed") == "completed"
    assert _legacy_status("failed") == "failed"
    assert _legacy_status("started") == "running"
    assert _legacy_status("indexing_code") == "running"
    assert _legacy_status("") == "running"


# --- _collect_warnings ------------------------------------------------


def test_collect_warnings_emits_one_per_failed_run() -> None:
    """Each failed run becomes a RepoScanWarning carrying its failing phase."""
    failed_run = _run(RepoRunStatus.FAILED)
    failed_run.error = "Boom"
    healthy_run = _run(RepoRunStatus.DONE)
    repo_name_by_id = {failed_run.repo_id: "broken-repo", healthy_run.repo_id: "ok-repo"}
    steps_by_run = {
        failed_run.id: [
            _step(ScanPhase.CODE_INDEX, StepStatus.DONE),
            _step(ScanPhase.SKILL_EXTRACTION, StepStatus.FAILED),
        ],
        healthy_run.id: [_step(ScanPhase.PERSIST_RESULTS, StepStatus.DONE)],
    }
    warnings = _collect_warnings([failed_run, healthy_run], steps_by_run, repo_name_by_id)
    assert len(warnings) == 1
    assert warnings[0].repo == "broken-repo"
    assert warnings[0].phase == ScanPhase.SKILL_EXTRACTION.value
    assert warnings[0].summary == "Boom"


def test_collect_warnings_falls_back_when_no_failed_step() -> None:
    """Failed run with no FAILED step still produces a warning labelled 'scan'."""
    run = _run(RepoRunStatus.FAILED)
    run.error = "Worker cancelled"
    repo_name_by_id = {run.repo_id: "stuck"}
    steps_by_run = {run.id: [_step(ScanPhase.REPO_SETUP, StepStatus.RUNNING)]}
    warnings = _collect_warnings([run], steps_by_run, repo_name_by_id)
    assert len(warnings) == 1
    assert warnings[0].phase == "scan"
    assert warnings[0].summary == "Worker cancelled"


# --- _render_phase_rows ----------------------------------------------


def test_render_phase_rows_marks_global_phases() -> None:
    """SKILL_REMAP / BACKEND_LINK / PERSIST_RESULTS are global scope."""
    run = _run()
    repo_name_by_id = {run.repo_id: "repo-x"}
    steps_by_run = {
        run.id: [
            _step(ScanPhase.REPO_SETUP, StepStatus.DONE),
            _step(ScanPhase.BACKEND_LINK, StepStatus.DONE),
        ]
    }
    rows = _render_phase_rows([run], steps_by_run, repo_name_by_id)
    by_phase = {row.phase: row for row in rows}
    assert by_phase[ScanPhase.REPO_SETUP.value].scope == "per_repo"
    assert by_phase[ScanPhase.REPO_SETUP.value].repo_name == "repo-x"
    assert by_phase[ScanPhase.BACKEND_LINK.value].scope == "global"
    # Global rows don't carry repo_id / repo_name.
    assert by_phase[ScanPhase.BACKEND_LINK.value].repo_id is None


def test_render_phase_rows_uses_humanised_label() -> None:
    """The label visible in the UI banner comes from _PHASE_LABELS."""
    run = _run()
    steps_by_run = {run.id: [_step(ScanPhase.CODE_INDEX, StepStatus.RUNNING)]}
    rows = _render_phase_rows([run], steps_by_run, {run.repo_id: "r"})
    assert rows[0].phase_label == "Indexing code"


def test_render_phase_rows_marks_sha_reused_for_skipped_cache() -> None:
    """SKIPPED_CACHE → ``sha_reused=True`` so the chip can render the ``cached`` badge."""
    run = _run()
    steps_by_run = {run.id: [_step(ScanPhase.CODE_INDEX, StepStatus.SKIPPED_CACHE)]}
    rows = _render_phase_rows([run], steps_by_run, {run.repo_id: "r"})
    assert rows[0].sha_reused is True


def test_render_phase_rows_no_sha_reused_for_running() -> None:
    run = _run()
    steps_by_run = {run.id: [_step(ScanPhase.CODE_INDEX, StepStatus.RUNNING)]}
    rows = _render_phase_rows([run], steps_by_run, {run.repo_id: "r"})
    assert rows[0].sha_reused is False


def _now() -> datetime:
    return datetime.now(UTC)
