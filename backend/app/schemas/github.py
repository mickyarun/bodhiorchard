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
    # The commit SHA written onto the base branch when the PR was merged.
    # Present on closed-merged events; absent on open/synchronize. This is
    # the only SHA guaranteed to land on `develop` regardless of merge
    # strategy (merge / squash / rebase) — the release-stage detector keys
    # off it to find which BUDs are included in a downstream release PR.
    merge_commit_sha: str | None = None


class GitHubReview(BaseModel):
    """PR review from a pull_request_review webhook."""

    id: int
    state: str  # APPROVED, CHANGES_REQUESTED, COMMENTED
    body: str | None = None
    html_url: str | None = None
    user: GitHubUser


class GitHubComment(BaseModel):
    """Comment from issue_comment or pull_request_review_comment webhook."""

    id: int
    body: str
    html_url: str
    user: GitHubUser
    created_at: str
    path: str | None = None  # Only on review comments (file path)
    line: int | None = None  # Only on review comments
    # Present on ``pull_request_review_comment`` payloads — links the inline
    # comment back to its parent review. Used by the webhook handler to
    # recognise GitHub's per-comment echo of a review the agent itself just
    # posted (the agent stages a ``review_id`` tag on its stored entries,
    # then both the review-summary event AND each comment event arrive).
    pull_request_review_id: int | None = None


class GitHubReviewThreadComment(BaseModel):
    """One comment carried inside a ``pull_request_review_thread`` payload.

    ``path`` + ``line`` are kept so we can match the thread back to a
    stored entry on its file location — agent-posted comments don't
    have ``github_comment_id`` populated locally (the per-comment echo
    is skipped to avoid duplicates), so id-only matching would miss
    every agent review thread.
    """

    id: int
    path: str | None = None
    line: int | None = None


class GitHubReviewThread(BaseModel):
    """Review-thread payload from ``pull_request_review_thread`` webhook.

    Fires with ``action: "resolved"`` when a reviewer clicks "Resolve
    conversation" on GitHub, and ``action: "unresolved"`` if they
    re-open it. The handler matches each stored ``code_review_comments``
    entry against the thread's comments — by ``github_comment_id`` for
    human-authored entries and by ``(file, line)`` for agent entries.
    """

    node_id: str
    comments: list[GitHubReviewThreadComment] = []
