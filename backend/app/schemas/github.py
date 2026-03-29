"""Pydantic schemas for GitHub webhook payloads.

Only parses fields we need — GitHub payloads are large and
we ignore most of the data.
"""

from pydantic import BaseModel


class GitHubUser(BaseModel):
    """GitHub user (sender, PR author, reviewer)."""

    login: str
    id: int


class GitHubRepository(BaseModel):
    """Repository from a GitHub webhook payload."""

    id: int
    full_name: str


class GitHubBranch(BaseModel):
    """Branch ref in a PR (head or base)."""

    ref: str
    sha: str


class GitHubPullRequest(BaseModel):
    """Pull request from a GitHub webhook payload."""

    id: int
    number: int
    title: str
    body: str | None = None
    html_url: str
    head: GitHubBranch
    base: GitHubBranch
    state: str
    user: GitHubUser
    merged: bool | None = False
    merged_at: str | None = None


class GitHubReview(BaseModel):
    """PR review from a pull_request_review webhook."""

    id: int
    state: str  # APPROVED, CHANGES_REQUESTED, COMMENTED
    user: GitHubUser
