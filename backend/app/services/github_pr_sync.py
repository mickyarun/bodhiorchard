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

        # Store comments in BUD regardless of GitHub post success
        if pr.bud_id:
            await _store_agent_comments_in_bud(db, org_id, pr.bud_id, matching, repo_name)

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

    Applies a fuzzy-signature dedup backstop against surviving non-agent
    comments (human GitHub reviews and manual frontend additions) so the
    Code Review Agent doesn't re-flag issues a human already surfaced.
    Old agent-sourced comments are expected to have already been cleared
    by `handle_code_review_result` before this function is called.
    """
    from app.repositories.bud import BUDRepository

    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_id_for_update(bud_id)
    if not bud:
        return

    existing = list(bud.code_review_comments or [])
    existing_sigs = {_comment_signature(c) for c in existing}
    now_iso = datetime.now(UTC).isoformat()

    added = 0
    skipped = 0
    for c in comments:
        new_entry = {
            "repo": repo_name,
            "file": c.get("file", ""),
            "line": c.get("line", 0),
            "body": c.get("comment", ""),
            "author": "bodhigrove-agent",
            "html_url": "",
            "created_at": now_iso,
            "is_summary": False,
            "source": "agent",
        }
        sig = _comment_signature(new_entry)
        if sig in existing_sigs:
            skipped += 1
            continue
        existing.append(new_entry)
        existing_sigs.add(sig)
        added += 1

    bud.code_review_comments = existing
    await db.flush()

    if skipped:
        logger.info(
            "agent_comments_dedup_skipped",
            bud_id=str(bud_id),
            repo=repo_name,
            added=added,
            skipped=skipped,
        )


def _comment_signature(c: dict) -> str:
    """Stable signature for dedup on (repo, file, body prefix).

    Lowercases and trims each field, then takes the first 120 chars of the
    body text. Handles the common case where two comments phrase the same
    issue slightly differently but agree on the location and lead sentence.
    Body falls back to the `comment` field for legacy entries that stored
    the text under that key.
    """
    repo = (c.get("repo") or "").strip().lower()
    file = (c.get("file") or "").strip().lower()
    body_raw = c.get("body") or c.get("comment") or ""
    body = body_raw.strip().lower()[:120]
    return f"{repo}|{file}|{body}"


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
