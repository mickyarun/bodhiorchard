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
    "setting_up_gitnexus": "Setting up GitNexus",
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


class KnowledgeItemRead(BaseModel):
    """Knowledge item for API response."""

    id: uuid.UUID
    title: str
    content: str | None
    category: str
    tags: list[str] | None = None
    source: str | None = None
    source_ref: str | None = Field(None, alias="sourceRef")
    feature_status: str | None = Field(None, alias="featureStatus")
    repo_ids: list[uuid.UUID] = Field(default_factory=list, alias="repoIds")

    model_config = {"populate_by_name": True, "from_attributes": True}


class KnowledgeItemPage(BaseModel):
    """Paginated response for the knowledge list endpoint."""

    items: list[KnowledgeItemRead]
    total: int

    model_config = {"populate_by_name": True}
