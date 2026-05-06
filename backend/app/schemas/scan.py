# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Pydantic schemas for the scan pipeline.

Two groups live here:

* **Internal pipeline DTOs** (``Community``, ``RunConfig``, ``StageResult``,
  ``TestRun``, ``StageStatus``, ``RunStatus``) — in-memory carriers passed
  between the workflow orchestrator and its stages. Mirrored to
  ``scan_repo_runs`` / ``scan_repo_steps`` via the DB observer.
* **External API request/response schemas** (``StartScanRequest``,
  ``ScanDetailResponse``, ``V2ConfigResponse``, etc.) consumed by
  ``app/api/v1/scans.py`` route handlers.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.scan_phase import ScanPhase
from app.models.scan_run_enums import RepoRunStatus, StepStatus
from app.models.tracked_repository import RepoStatus

StageStatus = Literal["queued", "running", "done", "failed", "skipped"]
RunStatus = Literal["queued", "running", "done", "failed"]


class Community(BaseModel):
    """One community after some reduction stage.

    Mirrors the shape of GitNexus ``Community`` nodes plus a few
    annotations (``drop_reason``, ``meta_community_id``) populated by
    later stages so the UI can show why something was kept or grouped.
    """

    label: str
    heuristic_label: str | None = None
    symbol_count: int = 0
    cohesion: float | None = None
    files: list[str] = Field(default_factory=list)
    drop_reason: str | None = None
    meta_community_id: str | None = None
    # GitNexus's unique node id (e.g. ``comm_42``). Optional because
    # post-merge meta-communities don't have a single source id; they
    # carry ``source_community_ids`` instead.
    community_id: str | None = None
    # Populated by ``merge_labels`` and ``hierarchical`` stages so the UI
    # can drill from a merged/meta row back to its constituent fragments.
    source_community_ids: list[str] = Field(default_factory=list)


class StageResult(BaseModel):
    """Outcome of a single stage in a scan run."""

    name: str
    status: StageStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    input_count: int = 0
    kept_count: int = 0
    dropped_count: int = 0
    config: dict[str, Any] = Field(default_factory=dict)
    extras: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


# Canonical per-repo stage list a scan walks by default. Order
# matters: each stage threads its kept communities into the next.
# Lives here (next to ``RunConfig``) so the schema's default_factory
# stays the single source of truth — orchestrators read this name
# rather than carrying their own copy.
DEFAULT_PER_REPO_STAGES: tuple[str, ...] = (
    "repo_setup",
    "ingest",
    "classify_repo",
    "extract",
    "merge_labels",
    "filter_infra",
    "hierarchical",
    "size_floor",
    "top_n",
    "synthesize",
    # ``extract_routes`` writes the per-backend ``backend_route_cache``;
    # the actual cross-layer linking is the global ``backend_link``
    # phase that runs after every per-repo workflow finishes.
    "extract_routes",
    "skill_extraction",
    "design_system",
)


class RunConfig(BaseModel):
    """Per-run configuration: which stages to run + each stage's params."""

    stages: list[str] = Field(default_factory=lambda: list(DEFAULT_PER_REPO_STAGES))
    merge_labels: dict[str, Any] = Field(default_factory=dict)
    filter_infra: dict[str, Any] = Field(default_factory=dict)
    hierarchical: dict[str, Any] = Field(default_factory=dict)
    size_floor: dict[str, Any] = Field(default_factory=dict)
    top_n: dict[str, Any] = Field(default_factory=dict)
    # Run-wide flags. ``full_rescan`` drives the soft-delete pre-hook
    # (every active repo's features get deactivated up-front when True;
    # only changed-SHA repos when False) and disables the skip-unchanged
    # short-circuit in ``_check_skip_unchanged``. Default ``False`` so a
    # request that omits the flag gets the cheap incremental path; the
    # frontend's "Full rescan" toggle opts in explicitly.
    full_rescan: bool = False


class TestRun(BaseModel):
    """Top-level in-memory run state passed between workflow stages."""

    # Stop pytest auto-collecting this Pydantic model as a test class.
    __test__ = False

    run_id: str
    repo_name: str
    repo_path: str
    config: RunConfig
    status: RunStatus = "queued"
    started_at: datetime
    finished_at: datetime | None = None
    stages: list[StageResult] = Field(default_factory=list)
    error: str | None = None


class TrackedRepoCard(BaseModel):
    """Repo tile rendered in the scan selection grid.

    The ``last_scan_*`` fields summarise the most recent ``ScanRepoRun``
    for this repo across every scan (not just the in-flight one). The
    Settings → Code list uses them to render a recency + status pill on
    rows that aren't part of the live scan, so the user can see at a
    glance which repos are stale, which succeeded, which failed.
    """

    id: uuid.UUID
    name: str
    path: str
    status: RepoStatus
    head_sha: str | None
    last_scanned_at: str | None
    feature_count: int
    last_scan_status: RepoRunStatus | None = None
    last_scan_finished_at: str | None = None
    last_scan_started_at: str | None = None
    last_scan_feature_count: int | None = None
    last_scan_id: uuid.UUID | None = None


class StartScanRequest(BaseModel):
    """POST /scans body — repo selection + per-stage config overrides."""

    repo_ids: list[uuid.UUID] = Field(default_factory=list)
    config: RunConfig = Field(default_factory=RunConfig)


class StartScanResponse(BaseModel):
    """Returned immediately after queueing a scan; clients poll GET /scans/{id}."""

    scan_id: uuid.UUID
    status: str
    repo_count: int


class ResumeScanResponse(BaseModel):
    """How many repo runs were re-queued by the resume call."""

    scan_id: uuid.UUID
    requeued: int


class StepRow(BaseModel):
    """One row of the scan timeline UI."""

    phase: ScanPhase
    status: StepStatus
    started_at: str | None
    finished_at: str | None
    duration_ms: int | None
    input_count: int
    kept_count: int
    dropped_count: int
    error: str | None
    # Per-stage payload — counts, derived labels, file samples, MCP
    # status, etc. The UI's debug panel pretty-prints this so an
    # operator can see exactly what each phase produced.
    extras: dict[str, Any] = Field(default_factory=dict)


class RepoRunRow(BaseModel):
    """One repo lane on the timeline."""

    repo_id: uuid.UUID
    repo_name: str
    status: RepoRunStatus
    head_sha_at_start: str | None
    started_at: str | None
    finished_at: str | None
    feature_count: int | None
    error: str | None
    steps: list[StepRow]


class ScanDetailResponse(BaseModel):
    """Full GET /scans/{id} payload — drives the timeline page."""

    scan_id: uuid.UUID
    status: str
    started_at: str
    repo_runs: list[RepoRunRow]


class V2ConfigResponse(BaseModel):
    """GET /config — single source of truth the frontend reads at boot.

    Frontend never duplicates the model name, max_turns, etc. — it
    fetches them from here so any tuning happens in one place.
    """

    default_model: str
    default_max_turns: int
    default_timeout_seconds: int
    known_phases: list[str]


class RepoScanWarning(BaseModel):
    """Per-repo failure surfaced on the legacy status endpoint."""

    repo: str
    phase: str
    summary: str
    hint: str | None = None


class PhaseStatusRow(BaseModel):
    """One row in the legacy per-phase timeline.

    Mirrors the frontend's ``PhaseStatus`` shape so SetupChecklist's
    polling adapter can stay unchanged when the backend pipeline moved.
    """

    phase: str
    phase_label: str = Field(serialization_alias="phaseLabel")
    scope: str
    repo_id: str | None = Field(default=None, serialization_alias="repoId")
    repo_name: str | None = Field(default=None, serialization_alias="repoName")
    status: str
    attempt: int = 1
    error_code: str | None = Field(default=None, serialization_alias="errorCode")
    error_message: str | None = Field(default=None, serialization_alias="errorMessage")
    started_at: str | None = Field(default=None, serialization_alias="startedAt")
    finished_at: str | None = Field(default=None, serialization_alias="finishedAt")
    sha_reused: bool = Field(default=False, serialization_alias="shaReused")

    model_config = {"populate_by_name": True}


class LegacyScanStatusResponse(BaseModel):
    """``GET /scans/{id}/status`` — legacy ``ScanStatusData`` shape.

    Renders ``Scan`` + ``ScanRepoRun`` + ``ScanRepoStep`` rows back
    into the flat shape the SetupChecklist component still expects.
    """

    scan_id: str = Field(serialization_alias="scanId")
    status: str
    status_label: str = Field(serialization_alias="statusLabel")
    scan_mode: str = Field(default="", serialization_alias="scanMode")
    progress_pct: float = Field(default=0.0, serialization_alias="progressPct")
    features_indexed: int = Field(default=0, serialization_alias="featuresIndexed")
    features_skipped: int = Field(default=0, serialization_alias="featuresSkipped")
    profiles_found: int = Field(default=0, serialization_alias="profilesFound")
    stale_cleaned: int = Field(default=0, serialization_alias="staleCleaned")
    unmatched_authors: list[str] = Field(
        default_factory=list, serialization_alias="unmatchedAuthors"
    )
    synthesis_warning: str | None = Field(default=None, serialization_alias="synthesisWarning")
    setup_pr_message: str | None = Field(default=None, serialization_alias="setupPrMessage")
    repo_warnings: list[RepoScanWarning] = Field(
        default_factory=list, serialization_alias="repoWarnings"
    )
    phases: list[PhaseStatusRow] = Field(default_factory=list)
    parent_scan_id: str | None = Field(default=None, serialization_alias="parentScanId")
    error: str | None = None

    model_config = {"populate_by_name": True}
