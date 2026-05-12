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

"""Code Review tab status aggregator.

Builds the per-impacted-repo view (PR state + comment count) shown on the
Code Review tab. The frontend uses this to display the PR status board and
decide whether to show the Override CTA.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.pull_request import PRState, PullRequest
from app.repositories.pull_request import PullRequestRepository

# An OPEN PR is the most informative state for "what's still in progress",
# so it should never be hidden by a later CLOSED/MERGED PR on the same repo.
# MERGED beats CLOSED because a merged PR is the positive outcome of review,
# while CLOSED-without-merge is a discarded attempt.
_PR_STATE_PRIORITY: dict[PRState, int] = {
    PRState.OPEN: 0,
    PRState.MERGED: 1,
    PRState.CLOSED: 2,
}


async def get_pr_status_summary(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> list[dict[str, Any]]:
    """Return per-impacted-repo PR status + comment count for the Code Review tab.

    For each repo in ``bud.impacted_repos``, looks up the most recent PR linked
    to this BUD (if any) and counts comments in ``bud.code_review_comments``
    that belong to the repo. Returns one dict per impacted repo with keys:

    - ``repo_id``: str — UUID of the tracked repo
    - ``repo_name``: str — short repo name
    - ``pr_number``: int | None — GitHub PR number, or ``None`` if no PR raised
    - ``pr_state``: str — ``not_raised`` | ``open`` | ``merged`` | ``closed``
    - ``pr_url``: str | None — PR HTML URL, or ``None`` if no PR raised
    - ``comment_count``: int — count of entries in ``bud.code_review_comments``
      whose ``repo`` matches ``repo_name``

    Returns an empty list if the BUD has no impacted repos.
    """
    impacted_repos = bud.impacted_repos or []
    if not impacted_repos:
        return []

    pr_repo = PullRequestRepository(db, org_id=org_id)
    prs = await pr_repo.list_for_bud(bud.id)

    # Collapse multiple PRs per repo by state priority (OPEN > MERGED > CLOSED).
    # Ties broken by list_for_bud's newest-first ordering. An open PR is never
    # hidden by a subsequently-created merged or closed PR on the same repo.
    pr_by_repo_id: dict[str, PullRequest] = {}
    for pr in prs:
        if pr.repo_id is None:
            continue
        key = str(pr.repo_id)
        existing = pr_by_repo_id.get(key)
        if existing is None or _PR_STATE_PRIORITY[pr.state] < _PR_STATE_PRIORITY[existing.state]:
            pr_by_repo_id[key] = pr

    # Count comments per repo name (webhook-synced + any agent-stored entries)
    comment_counts: dict[str, int] = {}
    for c in bud.code_review_comments or []:
        repo_name = c.get("repo")
        if repo_name:
            comment_counts[repo_name] = comment_counts.get(repo_name, 0) + 1

    result: list[dict[str, Any]] = []
    for ir in impacted_repos:
        repo_id = str(ir.get("repo_id", ""))
        repo_name = ir.get("repo_name", "")
        matched_pr: PullRequest | None = pr_by_repo_id.get(repo_id)

        if matched_pr is not None:
            pr_state = matched_pr.state.value
            pr_number: int | None = matched_pr.github_pr_number
            pr_url: str | None = matched_pr.html_url
        else:
            pr_state = "not_raised"
            pr_number = None
            pr_url = None

        result.append(
            {
                "repo_id": repo_id,
                "repo_name": repo_name,
                "pr_number": pr_number,
                "pr_state": pr_state,
                "pr_url": pr_url,
                "comment_count": comment_counts.get(repo_name, 0),
            }
        )

    return result
