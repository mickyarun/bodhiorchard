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

"""Pydantic schemas for the Jira import pipeline.

Covers: connection setup, project discovery, import configuration,
session tracking, status mapping, and reconciliation reporting.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ── Connection ────────────────────────────────────────────────────


class JiraConnectRequest(BaseModel):
    """Credentials for connecting to a Jira Cloud instance."""

    site_url: str = Field(..., alias="siteUrl", min_length=1, max_length=255)
    email: str = Field(..., min_length=1, max_length=255)
    api_token: str = Field(..., alias="apiToken", min_length=1)

    model_config = {"populate_by_name": True}


class JiraConnectionStatus(BaseModel):
    """Response after testing/saving Jira connection."""

    connected: bool
    cloud_id: str | None = Field(None, alias="cloudId")
    site_name: str | None = Field(None, alias="siteName")
    error: str | None = None

    model_config = {"populate_by_name": True}


# ── Project Discovery ─────────────────────────────────────────────


class JiraProjectSummary(BaseModel):
    """Summary of a Jira project available for import."""

    key: str
    name: str
    issue_count: int | None = Field(None, alias="issueCount")
    lead: str | None = None

    model_config = {"populate_by_name": True}


class JiraDiscoverRequest(BaseModel):
    """Request to scan a Jira project before import."""

    project_key: str = Field(
        ..., alias="projectKey", min_length=1, max_length=20, pattern=r"^[A-Z][A-Z0-9_]+$"
    )
    jql_filter: str | None = Field(None, alias="jqlFilter", max_length=1000)

    model_config = {"populate_by_name": True}


class IssueTypeCount(BaseModel):
    """Count of issues by type in discovery results."""

    issue_type: str = Field(..., alias="issueType")
    count: int

    model_config = {"populate_by_name": True}


class DiscoveryResult(BaseModel):
    """Results from scanning a Jira project."""

    project_key: str = Field(..., alias="projectKey")
    project_name: str = Field(..., alias="projectName")
    total_issues: int = Field(..., alias="totalIssues")
    by_type: list[IssueTypeCount] = Field(default_factory=list, alias="byType")
    statuses_found: list[str] = Field(default_factory=list, alias="statusesFound")
    estimated_time_seconds: int = Field(0, alias="estimatedTimeSeconds")
    already_imported_count: int = Field(0, alias="alreadyImportedCount")
    sample_issues: list[dict[str, Any]] = Field(default_factory=list, alias="sampleIssues")

    model_config = {"populate_by_name": True}


# ── Import Configuration ──────────────────────────────────────────


class JiraStatusMapping(BaseModel):
    """Maps a Jira status name to a BUD status."""

    jira_status: str = Field(..., alias="jiraStatus")
    bud_status: str = Field(..., alias="budStatus")

    model_config = {"populate_by_name": True}


class JiraTypeMapping(BaseModel):
    """Maps a Jira issue type to a target type (bud, bug, skip)."""

    jira_type: str = Field(..., alias="jiraType")
    target: str = Field(default="bud")  # "bud" | "bug" | "skip"

    model_config = {"populate_by_name": True}


class JiraImportRequest(BaseModel):
    """Request to start a Jira import run."""

    session_id: uuid.UUID = Field(..., alias="sessionId")
    consolidation_mode: str = Field(default="epic", alias="consolidationMode")  # "epic" | "flat"
    status_mappings: list[JiraStatusMapping] = Field(default_factory=list, alias="statusMappings")
    type_mappings: list[JiraTypeMapping] = Field(default_factory=list, alias="typeMappings")
    include_active: bool = Field(
        default=False,
        alias="includeActive",
        description="Include in-progress and done issues (default: backlog only)",
    )

    model_config = {"populate_by_name": True}


# ── Session Read ──────────────────────────────────────────────────


class JiraImportSessionRead(BaseModel):
    """Response schema for an import session."""

    id: uuid.UUID
    jira_project_key: str = Field(..., alias="jiraProjectKey")
    jira_project_name: str = Field(..., alias="jiraProjectName")
    status: str
    total_issues: int | None = Field(None, alias="totalIssues")
    processed_count: int = Field(0, alias="processedCount")
    discovery_result: DiscoveryResult | None = Field(None, alias="discoveryResult")
    result: "ReconciliationReport | None" = None
    error: str | None = None
    job_id: str | None = Field(None, alias="jobId")
    created_at: datetime = Field(..., alias="createdAt")

    model_config = {"populate_by_name": True, "from_attributes": True}


class JiraImportSessionList(BaseModel):
    """Lightweight session for list views."""

    id: uuid.UUID
    jira_project_key: str = Field(..., alias="jiraProjectKey")
    jira_project_name: str = Field(..., alias="jiraProjectName")
    status: str
    total_issues: int | None = Field(None, alias="totalIssues")
    processed_count: int = Field(0, alias="processedCount")
    created_at: datetime = Field(..., alias="createdAt")

    model_config = {"populate_by_name": True, "from_attributes": True}


# ── Reconciliation Report ─────────────────────────────────────────


class ImportedCounts(BaseModel):
    """Counts for successfully imported items."""

    buds_created: int = Field(0, alias="budsCreated")
    bugs_created: int = Field(0, alias="bugsCreated")
    consolidated_into_epics: int = Field(0, alias="consolidatedIntoEpics")
    subtasks_folded: int = Field(0, alias="subtasksFolded")

    model_config = {"populate_by_name": True}


class SkippedCounts(BaseModel):
    """Counts for skipped items."""

    exact_duplicates: int = Field(0, alias="exactDuplicates")
    semantic_duplicates: int = Field(0, alias="semanticDuplicates")
    merged_similar: int = Field(0, alias="mergedSimilar")

    model_config = {"populate_by_name": True}


class ReviewItem(BaseModel):
    """An item flagged for manual duplicate review."""

    jira_key: str = Field(..., alias="jiraKey")
    summary: str = ""
    description_preview: str = Field("", alias="descriptionPreview")
    issue_type: str = Field("", alias="issueType")
    similar_to_bud: int | None = Field(None, alias="similarToBud")
    distance: float

    model_config = {"populate_by_name": True}


class FailedItem(BaseModel):
    """An item that failed to import."""

    jira_key: str = Field(..., alias="jiraKey")
    error: str

    model_config = {"populate_by_name": True}


class ReconciliationReport(BaseModel):
    """Full reconciliation report after an import completes."""

    total_jira_issues: int = Field(0, alias="totalJiraIssues")
    imported: ImportedCounts = Field(default_factory=ImportedCounts)
    skipped: SkippedCounts = Field(default_factory=SkippedCounts)
    review_needed: list[ReviewItem] = Field(default_factory=list, alias="reviewNeeded")
    failed: list[FailedItem] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ── Job Payloads ──────────────────────────────────────────────────


class JiraDiscoveryPayload(BaseModel):
    """Payload for the jira_discovery job queue entry."""

    org_id: str
    session_id: str
    project_key: str
    jql_filter: str | None = None


class JiraImportPayload(BaseModel):
    """Payload for the jira_import job queue entry."""

    org_id: str
    session_id: str
