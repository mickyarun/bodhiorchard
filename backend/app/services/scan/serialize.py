# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Helpers that turn raw scan ORM rows into API response shapes.

Pulled out of ``scans_api.py`` so the route file stays focused on
HTTP concerns. Each helper takes a session + scoped ids and returns
already-serialised Pydantic objects ready for the JSON response.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.synthesis_accumulator import peek_titles
from app.models.feature import Feature
from app.models.scan import Scan, ScanAggregateStatus
from app.models.scan_phase import ScanPhase
from app.models.scan_repo_run import ScanRepoRun
from app.models.scan_repo_step import ScanRepoStep
from app.models.scan_run_enums import RepoRunStatus, StepStatus
from app.repositories.feature import FeatureRepository
from app.repositories.scan_run import ScanRunRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.scan import (
    LegacyScanStatusResponse,
    PhaseStatusRow,
    RepoRunRow,
    RepoScanWarning,
    StepRow,
)

# Phases whose review-able artifact is the feature list. FEATURE_SYNTHESIS
# is the writer; the legacy FEATURE_MERGE chip is no longer rendered as
# the merge phase has been removed from the pipeline.
_FEATURE_ARTIFACT_PHASES = frozenset({ScanPhase.FEATURE_SYNTHESIS})


async def build_repo_run_rows(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
) -> list[RepoRunRow]:
    """Render one scan: runs + steps + repo names + synthesized artifacts.

    The synthesized-feature lookup lets the FEATURE_SYNTHESIS chip
    surface real titles in the popover instead of just count metadata
    in ``extras`` — the user reviews the actual artifacts there.
    """
    run_repo = ScanRunRepository(db, org_id=org_id)
    runs = await run_repo.find_for_scan(scan_id=scan_id)
    if not runs:
        return []

    repo_name_by_id = await TrackedRepoRepository(db, org_id=org_id).get_names_by_ids(
        [r.repo_id for r in runs]
    )
    steps_by_run = await run_repo.find_steps_grouped_by_run(run_ids=[r.id for r in runs])
    features_by_repo = await FeatureRepository(db, org_id=org_id).list_active_grouped_by_repos(
        [r.repo_id for r in runs]
    )

    return [
        _render_repo_run(run, repo_name_by_id, steps_by_run, features_by_repo, org_id=org_id)
        for run in runs
    ]


def _render_repo_run(
    run: ScanRepoRun,
    repo_name_by_id: dict[uuid.UUID, str],
    steps_by_run: dict[uuid.UUID, list[ScanRepoStep]],
    features_by_repo: dict[uuid.UUID, list[Feature]],
    *,
    org_id: uuid.UUID,
) -> RepoRunRow:
    """Convert one run + its steps to the API shape."""
    repo_features = features_by_repo.get(run.repo_id, [])
    # Mid-synthesis the reconciler hasn't drained yet, so the DB has no
    # rows for this repo. Read titles directly from the in-memory MCP
    # accumulator so the running chip's popover shows progress instead
    # of an empty "0 → 0/0" frame.
    pending_titles = peek_titles(str(org_id), str(run.repo_id)) if not repo_features else []
    return RepoRunRow(
        repo_id=run.repo_id,
        repo_name=repo_name_by_id.get(run.repo_id, "(unknown)"),
        status=run.status,
        head_sha_at_start=run.head_sha_at_start,
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        feature_count=run.feature_count,
        error=run.error,
        steps=[
            _render_step(step, repo_features, pending_titles=pending_titles)
            for step in steps_by_run.get(run.id, [])
        ],
    )


def _render_step(
    step: ScanRepoStep,
    repo_features: list[Feature],
    *,
    pending_titles: list[dict[str, str]],
) -> StepRow:
    """Convert one ScanRepoStep ORM row to its API shape.

    For artifact-producing phases we attach the human-readable items
    onto ``extras`` so the popover can render review-able lists
    (titles, descriptions) instead of just stage metadata. While
    ``feature_synthesis`` is still ``running``, the DB is empty (the
    reconciler drains the accumulator only at end-of-batch) so we
    render the in-memory ``pending_titles`` instead.
    """
    extras = dict(step.extras) if step.extras else {}
    if step.phase in _FEATURE_ARTIFACT_PHASES:
        if repo_features:
            extras["produced_features"] = [
                {
                    "title": f.feature_title,
                    "description": f.description,
                }
                for f in repo_features
            ]
        elif step.status == StepStatus.RUNNING and pending_titles:
            extras["produced_features"] = list(pending_titles)
    return StepRow(
        phase=step.phase,
        status=step.status,
        started_at=step.started_at.isoformat() if step.started_at else None,
        finished_at=step.finished_at.isoformat() if step.finished_at else None,
        duration_ms=step.duration_ms,
        input_count=step.input_count,
        kept_count=step.kept_count,
        dropped_count=step.dropped_count,
        error=step.error,
        extras=extras,
    )


# ── Legacy ScanStatusData adapter ──────────────────────────────────
# SetupChecklist + ScanPhaseTimeline still consume the old flat shape;
# rather than rewrite those components, we render the scan ORM rows back
# into the legacy shape on demand.

_TERMINAL_STEP_STATUSES = frozenset({StepStatus.DONE, StepStatus.FAILED, StepStatus.SKIPPED_CACHE})


_PHASE_LABELS: dict[ScanPhase, str] = {
    ScanPhase.MODE_DETECTION: "Detecting scan mode",
    ScanPhase.REPO_SETUP: "Repo setup",
    ScanPhase.CODE_INDEX: "Indexing code",
    ScanPhase.STALE_CLEANUP: "Cleaning stale items",
    ScanPhase.SKILL_EXTRACTION: "Analysing skills",
    ScanPhase.DESIGN_SYSTEM_EXTRACT: "Extracting design system",
    ScanPhase.FEATURE_SYNTHESIS: "Synthesising features",
    ScanPhase.EXTRACT_ROUTES: "Extracting backend routes",
    ScanPhase.SKILL_REMAP: "Remapping skills",
    ScanPhase.BACKEND_LINK: "Linking backend routes",
    ScanPhase.EMBEDDING_BACKFILL: "Generating embeddings",
    ScanPhase.PERSIST_RESULTS: "Saving results",
}


# Phases that run once across the whole scan after every per-repo
# workflow has finished. Anything else in ``_PHASE_LABELS`` is per-repo.
_GLOBAL_PHASES = frozenset(
    {ScanPhase.SKILL_REMAP, ScanPhase.BACKEND_LINK, ScanPhase.PERSIST_RESULTS}
)


# Derive phase counts from the label table + global-phase set so adding
# a new ScanPhase here keeps the progress denominator in sync. Computing
# these eagerly at import time means a typo (e.g. a global phase missing
# from ``_PHASE_LABELS``) shows up immediately rather than as a sticky
# 100% UI bug at runtime.
_GLOBAL_PHASE_COUNT = len(_GLOBAL_PHASES)
_PER_REPO_PHASE_COUNT = len(_PHASE_LABELS) - _GLOBAL_PHASE_COUNT


async def build_legacy_status(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    scan: Scan,
) -> LegacyScanStatusResponse:
    """Render scan state back into the legacy ``ScanStatusData`` shape."""
    run_repo = ScanRunRepository(db, org_id=org_id)
    runs = await run_repo.find_for_scan(scan_id=scan.id)
    repo_name_by_id = await TrackedRepoRepository(db, org_id=org_id).get_names_by_ids(
        [r.repo_id for r in runs]
    )
    steps_by_run = await run_repo.find_steps_grouped_by_run(run_ids=[r.id for r in runs])

    return LegacyScanStatusResponse(
        scan_id=str(scan.id),
        status=_legacy_status(scan.status),
        status_label=_humanize_status(scan.status),
        progress_pct=_compute_progress(runs, steps_by_run),
        features_indexed=sum(r.feature_count or 0 for r in runs),
        repo_warnings=_collect_warnings(runs, steps_by_run, repo_name_by_id),
        phases=_render_phase_rows(runs, steps_by_run, repo_name_by_id),
        error=scan.error,
    )


def _legacy_status(status_str: str) -> str:
    """Map the enum string to the three buckets the frontend expects."""
    if status_str == ScanAggregateStatus.COMPLETED.value:
        return "completed"
    if status_str == ScanAggregateStatus.FAILED.value:
        return "failed"
    return "running"


def _humanize_status(status_str: str) -> str:
    """Turn ``"indexing_code"`` into ``"Indexing code"`` for the UI banner."""
    return status_str.replace("_", " ").capitalize() if status_str else ""


def _compute_progress(
    runs: list[ScanRepoRun],
    steps_by_run: dict[uuid.UUID, list[ScanRepoStep]],
) -> float:
    """Estimate progress as distinct-terminal-phases / expected-phases.

    Counts unique ``(scan_repo_run_id, phase)`` pairs that have reached
    a terminal status. Naive step-counting double-counts on Resume —
    previously-DONE step rows survive the re-queue and get counted
    alongside the freshly-running ones, capping the bar at 100% before
    the global phases finish. Distinct-pair counting avoids that.
    """
    if not runs:
        return 0.0
    total_expected = len(runs) * _PER_REPO_PHASE_COUNT + _GLOBAL_PHASE_COUNT
    terminal_pairs: set[tuple[uuid.UUID, ScanPhase]] = set()
    for run_id, steps in steps_by_run.items():
        for step in steps:
            if step.status in _TERMINAL_STEP_STATUSES:
                terminal_pairs.add((run_id, step.phase))
    return min(100.0, (len(terminal_pairs) / total_expected) * 100.0)


def _collect_warnings(
    runs: list[ScanRepoRun],
    steps_by_run: dict[uuid.UUID, list[ScanRepoStep]],
    repo_name_by_id: dict[uuid.UUID, str],
) -> list[RepoScanWarning]:
    """One warning per failed repo run — surface the failing phase."""
    warnings: list[RepoScanWarning] = []
    for run in runs:
        if run.status != RepoRunStatus.FAILED:
            continue
        steps = steps_by_run.get(run.id, [])
        failed_step = next((s for s in steps if s.status == StepStatus.FAILED), None)
        warnings.append(
            RepoScanWarning(
                repo=repo_name_by_id.get(run.repo_id, "(unknown)"),
                phase=failed_step.phase.value if failed_step else "scan",
                summary=run.error or (failed_step.error if failed_step else "Scan failed"),
                hint=None,
            )
        )
    return warnings


def _render_phase_rows(
    runs: list[ScanRepoRun],
    steps_by_run: dict[uuid.UUID, list[ScanRepoStep]],
    repo_name_by_id: dict[uuid.UUID, str],
) -> list[PhaseStatusRow]:
    """One PhaseStatusRow per (repo, phase) plus aggregated rows for global phases."""
    rows: list[PhaseStatusRow] = []
    for run in runs:
        for step in steps_by_run.get(run.id, []):
            scope = "global" if step.phase in _GLOBAL_PHASES else "per_repo"
            rows.append(
                PhaseStatusRow(
                    phase=step.phase.value,
                    phase_label=_PHASE_LABELS.get(step.phase, step.phase.value),
                    scope=scope,
                    repo_id=str(run.repo_id) if scope == "per_repo" else None,
                    repo_name=repo_name_by_id.get(run.repo_id) if scope == "per_repo" else None,
                    status=step.status.value,
                    error_message=step.error,
                    started_at=step.started_at.isoformat() if step.started_at else None,
                    finished_at=step.finished_at.isoformat() if step.finished_at else None,
                    sha_reused=step.status == StepStatus.SKIPPED_CACHE,
                )
            )
    return rows
