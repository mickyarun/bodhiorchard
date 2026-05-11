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

"""Sync code review comments from BUD to GitHub PRs.

Maps agent-generated code review comments to GitHub PR review
comments and posts them via the GitHub API.
"""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.pull_request import PRState
from app.repositories.pull_request import PullRequestRepository
from app.services.github_app_auth import get_installation_token
from app.services.github_client import GitHubClient

logger = structlog.get_logger(__name__)


async def sync_review_comments_to_github(
    bud_id: uuid.UUID,
    org_id: uuid.UUID,
    comments: list[dict],
    db: AsyncSession,
) -> None:
    """Persist agent review comments locally and post to any open PRs.

    Comments are always stored locally in ``bud.code_review_comments``
    (so the Code Review tab's comment-count badges reflect the agent's
    output) regardless of whether an open GitHub PR exists to post to.
    When PRs do exist, comments are also posted as inline PR reviews via
    the GitHub API. Partial failures on the GitHub side do not prevent
    local storage.

    Args:
        bud_id: BUD whose comments to sync.
        org_id: Organization UUID.
        comments: Agent-generated code_review_comments list.
        db: Async database session.
    """
    if not comments:
        return

    # Group comments by repo name first — used for both local storage and
    # GitHub post matching.
    by_repo: dict[str, list[dict]] = {}
    for c in comments:
        repo = c.get("repo", "")
        if repo:
            by_repo.setdefault(repo, []).append(c)

    # Local storage ALWAYS runs, independent of GitHub connectivity. This
    # guarantees the Code Review tab shows the agent's output even when
    # the GitHub App isn't installed, the token is missing, or no PR has
    # been raised yet.
    for repo_name, matching in by_repo.items():
        await _store_agent_comments_in_bud(db, org_id, bud_id, matching, repo_name)

    # GitHub posting is best-effort from here on.
    org = await db.get(Organization, org_id)
    if not org:
        logger.warning("github_sync_skip_no_org", org_id=str(org_id), bud_id=str(bud_id))
        return

    token = await get_installation_token(org)
    if not token:
        logger.warning(
            "github_sync_skip_no_token",
            org_id=str(org_id),
            bud_id=str(bud_id),
        )
        return

    client = GitHubClient(token)
    pr_repo = PullRequestRepository(db, org_id=org_id)
    prs = await pr_repo.list_for_bud(bud_id)
    open_prs = [pr for pr in prs if pr.state == PRState.OPEN]

    if not open_prs:
        logger.info(
            "github_sync_no_open_prs",
            bud_id=str(bud_id),
            comment_count=len(comments),
        )
        return

    for pr in open_prs:
        repo_name = pr.github_repo_full_name.split("/")[-1]
        matching = by_repo.get(repo_name, [])
        if not matching:
            continue

        # Skip if we already posted a review for this set
        meta = pr.metadata_ or {}
        if meta.get("review_synced"):
            continue

        gh_comments = _map_to_github_comments(matching)
        body = f"Automated code review by BodhiOrchard ({len(matching)} comment(s))"

        try:
            result = await client.create_pr_review(
                pr.github_repo_full_name,
                pr.github_pr_number,
                body=body,
                comments=gh_comments if gh_comments else None,
            )
        except Exception:
            logger.exception(
                "github_sync_post_failed",
                pr_number=pr.github_pr_number,
                bud_id=str(bud_id),
            )
            continue

        if result:
            pr.metadata_ = {**(pr.metadata_ or {}), "review_synced": True}
            await db.flush()
            logger.info(
                "github_review_posted",
                pr_number=pr.github_pr_number,
                comment_count=len(matching),
            )


async def _store_agent_comments_in_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    comments: list[dict],
    repo_name: str,
) -> None:
    """Store agent-generated review comments directly in the BUD.

    Called from ``sync_review_comments_to_github`` after posting agent
    comments to a GitHub PR. The stored entries feed the comment-count
    badges on the Code Review tab's per-repo status board.

    On each call, existing ``source: "agent"`` entries for ``repo_name``
    are cleared before appending the new batch. This makes the operation
    idempotent under task retries and re-runs: the stored agent comments
    always reflect the most recent agent output, never a superset across
    runs. Human-authored entries (``source: "github"`` from webhooks and
    anything else) are untouched.
    """
    from app.repositories.bud import BUDRepository

    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_id_for_update(bud_id)
    if not bud:
        return

    # Drop previous agent entries for THIS repo only — preserves agent
    # comments from sibling repos processed earlier in the same sync loop
    # and all non-agent entries.
    existing = [
        c
        for c in (bud.code_review_comments or [])
        if not (c.get("source") == "agent" and c.get("repo") == repo_name)
    ]
    now_iso = datetime.now(UTC).isoformat()

    for c in comments:
        existing.append(
            {
                "repo": repo_name,
                "file": c.get("file", ""),
                "line": c.get("line", 0),
                "body": c.get("comment", ""),
                "author": "bodhiorchard-agent",
                "html_url": "",
                "created_at": now_iso,
                "is_summary": False,
                "source": "agent",
            }
        )

    bud.code_review_comments = existing
    await db.flush()


def _map_to_github_comments(comments: list[dict]) -> list[dict]:
    """Convert agent comments to GitHub review comment format."""
    gh_comments = []
    for c in comments:
        file_path = c.get("file", "")
        line = c.get("line")
        comment_body = c.get("comment", "")
        severity = c.get("severity", "suggestion")

        if not file_path or not comment_body:
            continue

        prefix = {"error": "**Error:**", "warning": "**Warning:**"}.get(
            severity, "**Suggestion:**"
        )

        entry: dict = {
            "path": file_path,
            "body": f"{prefix} {comment_body}",
        }
        if line and isinstance(line, int):
            entry["line"] = line

        gh_comments.append(entry)

    return gh_comments
