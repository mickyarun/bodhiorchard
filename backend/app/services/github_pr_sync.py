"""Sync code review comments from BUD to GitHub PRs.

Maps agent-generated code review comments to GitHub PR review
comments and posts them via the GitHub API.
"""

import uuid

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
    """Post code review comments to linked GitHub PRs.

    Groups comments by repo, matches to open PRs, and posts
    via GitHub API. Idempotent — skips PRs already reviewed.

    Args:
        bud_id: BUD whose comments to sync.
        org_id: Organization UUID.
        comments: Agent-generated code_review_comments list.
        db: Async database session.
    """
    if not comments:
        return

    org = await db.get(Organization, org_id)
    if not org:
        return

    token = await get_installation_token(org)
    if not token:
        logger.debug("github_sync_skip_no_token", org_id=str(org_id))
        return

    client = GitHubClient(token)
    pr_repo = PullRequestRepository(db, org_id=org_id)
    prs = await pr_repo.list_for_bud(bud_id)
    open_prs = [pr for pr in prs if pr.state == PRState.OPEN]

    if not open_prs:
        return

    # Group comments by repo name
    by_repo: dict[str, list[dict]] = {}
    for c in comments:
        repo = c.get("repo", "")
        by_repo.setdefault(repo, []).append(c)

    for pr in open_prs:
        # Match PR to comments by repo name (last segment of full_name)
        repo_name = pr.github_repo_full_name.split("/")[-1]
        matching = by_repo.get(repo_name, [])
        if not matching:
            continue

        # Skip if we already posted a review for this set
        meta = pr.metadata_ or {}
        if meta.get("review_synced"):
            continue

        # Map to GitHub inline comment format
        gh_comments = _map_to_github_comments(matching)
        body = f"Automated code review by BodhiGrove ({len(matching)} comment(s))"

        result = await client.create_pr_review(
            pr.github_repo_full_name,
            pr.github_pr_number,
            body=body,
            comments=gh_comments if gh_comments else None,
        )

        if result:
            pr.metadata_ = {**(pr.metadata_ or {}), "review_synced": True}
            await db.flush()
            logger.info(
                "github_review_posted",
                pr_number=pr.github_pr_number,
                comment_count=len(matching),
            )


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
