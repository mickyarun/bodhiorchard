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

"""Pydantic schemas for developer activity, commits, and effectiveness metrics."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CommitRepoRead(BaseModel):
    """Schema for a repo with commit info for a BUD."""

    repo_path: str
    repo_name: str
    commit_count: int
    first_sha: str
    last_sha: str


class UntrackedRepoRead(BaseModel):
    """Schema for a repo with commits but NOT in tracked_repositories.

    Surfaced separately from ``CommitRepoRead`` so the BUD detail testing
    tab can render an "Add as tracked" CTA. The QA tester (or anyone else)
    pushed activity from a path the org hasn't added yet — the row exists
    in dev_activity_logs but couldn't resolve to a tracked_repositories.id.
    """

    repo_path: str
    name: str
    commit_count: int


class DevActivityRead(BaseModel):
    """Schema for a single developer activity entry."""

    id: uuid.UUID
    event_type: str
    status: str | None = None
    message: str | None = None
    source: str
    actor_name: str | None = None
    session_id: str | None = None
    branch: str | None = None
    commit_sha: str | None = None
    file_path: str | None = None
    metadata: dict[str, Any] | None = Field(None, validation_alias="metadata_")
    created_at: datetime

    model_config = {"from_attributes": True}


class DevCommitRead(BaseModel):
    """Schema for a single BUD commit."""

    commit_sha: str
    commit_message: str
    branch_name: str
    files_changed: str
    repo_path: str
    author_name: str | None = None
    author_email: str | None = None
    user_id: uuid.UUID | None = None
    user_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ContributorRead(BaseModel):
    """A developer who has contributed to a BUD."""

    user_id: str | None = None
    user_name: str | None = None
    author_name: str | None = None
    author_email: str | None = None
    commit_count: int = 0
    files_changed: int = 0
    commits: list[DevCommitRead] = []


class DevStatsRead(BaseModel):
    """Aggregated development stats for a BUD."""

    total_commits: int = 0
    total_files_changed: int = 0
    repos_touched: int = 0
    agent_runs: int = 0
    effectiveness_score: int = 0
    confidence: float = 0.0
    completion_rate: float = 0.0
    cost_per_commit: float = 0.0
    total_cost_usd: float = 0.0
    test_coverage: str = "none"
    risk_count: int = 0


class DevActivityResponse(BaseModel):
    """Full development activity response."""

    activities: list[DevActivityRead] = []
    commits: list[DevCommitRead] = []
    contributors: list[ContributorRead] = []
    repos: list[CommitRepoRead] = []
    untracked_repos: list[UntrackedRepoRead] = []
    stats: DevStatsRead = DevStatsRead()


# ── Claude Code Hook Schemas ─────────────────────────────────────


class DevActivityHookRequest(BaseModel):
    """Request body for Claude Code hook activity reports.

    Sent by hook scripts (session-start, post-commit-track, activity-report)
    to POST /mcp/dev-activity with Bearer token auth.
    """

    session_id: str = Field(default="", max_length=100)
    event_type: Literal[
        "session_start",
        "session_end",
        "activity_summary",
        "commit",
        "file_change",
        "tool_call",
        "tool_error",
        "api_error",
        "user_prompt",
        "subagent_start",
        "subagent_stop",
    ]
    bud_number: int | None = None
    author_email: str = Field(default="", max_length=255)
    branch: str = Field(default="", max_length=500)
    repo_path: str = Field(default="", max_length=1000)
    message: str = Field(default="", max_length=2000)
    commit_sha: str = Field(default="", max_length=40)
    file_path: str = Field(default="", max_length=1000)
    files_changed: str = Field(default="", max_length=5000)
    metadata: dict[str, Any] | None = None


class DevActivityHookResponse(BaseModel):
    """Response for Claude Code hook activity reports."""

    success: bool
    event_type: str
    bud_number: int | None = None
    user_resolved: bool = False
    error: str | None = None
