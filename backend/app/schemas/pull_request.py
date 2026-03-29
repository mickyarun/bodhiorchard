"""Pydantic schemas for pull request API responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PullRequestRead(BaseModel):
    """API response for a single pull request."""

    id: uuid.UUID
    bud_id: uuid.UUID | None = None
    repo_id: uuid.UUID | None = None
    github_pr_number: int
    github_repo_full_name: str
    title: str
    html_url: str
    head_branch: str
    base_branch: str
    state: str
    review_status: str
    author_github_login: str
    merged_at: datetime | None = None
    metadata: dict | None = Field(None, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PRChecklistItem(BaseModel):
    """One repo's PR status in the merge checklist."""

    repo_id: str
    repo_name: str
    pr: PullRequestRead | None = None
    status: str  # "no_pr" | "open" | "merged"
