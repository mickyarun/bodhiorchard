# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Pydantic schemas for skill scanning, knowledge search, and profiles."""

import uuid

from pydantic import BaseModel, Field, computed_field


class ScanRequest(BaseModel):
    """Request to trigger a repository scan."""

    full_rescan: bool = Field(default=False, alias="fullRescan")

    model_config = {"populate_by_name": True}


class ScanResponse(BaseModel):
    """Response after triggering a scan."""

    scan_id: str = Field(alias="scanId")
    status: str = "started"

    model_config = {"populate_by_name": True}


STATUS_LABELS: dict[str, str] = {
    "started": "Starting scan",
    "checking_out": "Checking out repository",
    "analyzing_changes": "Analyzing changes",
    "indexing_code": "Indexing code structure",
    "setting_up_index": "Setting up code index",
    "setting_up_worktrees": "Configuring worktrees",
    "setting_up_mcp": "Setting up Bodhiorchard MCP",
    "installing_hooks": "Installing git hooks",
    "pushing_setup": "Pushing setup files",
    "cleaning_stale": "Cleaning stale references",
    "analyzing_skills": "Analyzing developer skills",
    "extracting_design_system": "Extracting design system",
    "synthesizing_features": "Synthesizing features",
    "generating_embeddings": "Generating embeddings",
    "merging_features": "Merging cross-repo features",
    "remapping_skills": "Remapping skills to features",
    "saving_results": "Saving results",
    "finalizing": "Finalizing",
    "finalizing_repo": "Finalizing repository",
    "completed": "Scan complete",
    "failed": "Scan failed",
}


class RepoScanWarning(BaseModel):
    """A non-fatal failure surfaced to the UI for a (repo, phase) pair."""

    repo: str
    phase: str
    summary: str
    hint: str | None = None


class PhaseStatus(BaseModel):
    """One row of the per-phase timeline the frontend renders.

    Derived from a ``scan_phase_checkpoints`` row with three extras:

    - ``phase_label`` — the human-readable name (same pattern as
      ``ScanStatus.status_label``).
    - ``repo_name`` — resolved from ``tracked_repositories`` so the
      timeline doesn't have to do a separate lookup.
    - ``sha_reused`` — ``True`` when ``started_at == finished_at``,
      which is how ``insert_reused`` marks a row copied from a prior
      scan's cached payload.

    All fields are optional so the same DTO can describe either a
    fresh running phase or a terminal checkpoint.
    """

    phase: str
    phase_label: str = Field(alias="phaseLabel")
    scope: str
    repo_id: str | None = Field(default=None, alias="repoId")
    repo_name: str | None = Field(default=None, alias="repoName")
    status: str
    attempt: int = 1
    error_code: str | None = Field(default=None, alias="errorCode")
    error_message: str | None = Field(default=None, alias="errorMessage")
    started_at: str | None = Field(default=None, alias="startedAt")
    finished_at: str | None = Field(default=None, alias="finishedAt")
    sha_reused: bool = Field(default=False, alias="shaReused")

    model_config = {"populate_by_name": True}


_PHASE_LABELS: dict[str, str] = {
    "mode_detection": "Detecting changes",
    "code_index": "Indexing code structure",
    "repo_setup": "Setting up repository",
    "stale_cleanup": "Cleaning stale references",
    "skill_extraction": "Analysing developer skills",
    "design_system_extract": "Extracting design system",
    "feature_synthesis": "Synthesising features",
    "skill_remap": "Remapping skills to features",
    "feature_merge": "Merging cross-repo features",
    "embedding_backfill": "Generating embeddings",
    "persist_results": "Saving results",
}


def phase_label(phase: str) -> str:
    """Human-readable label for a ``ScanPhase`` value, with a safe fallback."""
    return _PHASE_LABELS.get(phase, phase.replace("_", " ").capitalize())


class ScanStatus(BaseModel):
    """Status of a running or completed scan."""

    scan_id: str = Field(alias="scanId")
    status: str
    scan_mode: str = Field(default="full", alias="scanMode")
    progress_pct: int = Field(default=0, alias="progressPct")
    features_indexed: int = Field(default=0, alias="featuresIndexed")
    features_skipped: int = Field(default=0, alias="featuresSkipped")
    profiles_found: int = Field(default=0, alias="profilesFound")
    stale_cleaned: int = Field(default=0, alias="staleCleaned")
    unmatched_authors: list[str] = Field(default_factory=list, alias="unmatchedAuthors")
    synthesis_warning: str | None = Field(default=None, alias="synthesisWarning")
    setup_pr_message: str | None = Field(default=None, alias="setupPrMessage")
    repo_warnings: list[RepoScanWarning] = Field(default_factory=list, alias="repoWarnings")
    phases: list[PhaseStatus] = Field(default_factory=list)
    parent_scan_id: str | None = Field(default=None, alias="parentScanId")
    error: str | None = None

    @computed_field(alias="statusLabel")  # type: ignore[misc]
    @property
    def status_label(self) -> str:
        """Human-readable label for the current status."""
        return STATUS_LABELS.get(self.status, self.status)

    model_config = {"populate_by_name": True}


class ModuleSkill(BaseModel):
    """A single module skill entry within a profile."""

    name: str
    score: float
    languages: list[str] = []
    touch_count: int = Field(alias="touchCount")

    model_config = {"populate_by_name": True}


class SkillProfileRead(BaseModel):
    """Developer skill profile for API response."""

    user_id: uuid.UUID | None = Field(None, alias="userId")
    user_name: str = Field(alias="userName")
    email: str
    modules: list[ModuleSkill] = []

    model_config = {"populate_by_name": True}
