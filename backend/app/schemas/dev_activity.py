"""Pydantic schemas for developer activity, commits, and effectiveness metrics."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CommitRepoRead(BaseModel):
    """Schema for a repo with commit info for a BUD."""

    repo_path: str
    repo_name: str
    commit_count: int
    first_sha: str
    last_sha: str


class DevActivityRead(BaseModel):
    """Schema for a single developer activity entry."""

    id: uuid.UUID
    status: str
    message: str
    source: str
    actor_name: str | None = None
    metadata: dict | None = Field(None, validation_alias="metadata_")
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
    stats: DevStatsRead = DevStatsRead()
