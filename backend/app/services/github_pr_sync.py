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
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.pull_request import PRState
from app.repositories.bud import BUDRepository
from app.repositories.pull_request import PullRequestRepository
from app.services.github_app_auth import get_installation_token
from app.services.github_client import GitHubClient

logger = structlog.get_logger(__name__)


async def sync_review_comments_to_github(
    bud_id: uuid.UUID,
    org_id: uuid.UUID,
    comments: list[dict[str, Any]],
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
    by_repo: dict[str, list[dict[str, Any]]] = {}
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

        # No sticky ``review_synced`` short-circuit here. The real dedup
        # mechanism is the per-comment ``review_id`` tag written by
        # ``_tag_agent_review_id`` — the webhook handler uses that to
        # suppress GitHub's echo of our own review. A PR-level flag
        # would block re-runs entirely: every subsequent code-review
        # agent run on the same BUD would store its comments locally
        # but never reach GitHub, leaving the PR perpetually showing
        # the first run's review while the BUD-tab count keeps growing.
        #
        # KNOWN GAP: two *concurrent* sync calls against the same PR
        # row will both reach the POST and double-post. A SELECT … FOR
        # UPDATE on ``pull_requests`` (or an advisory lock keyed by
        # ``pr.id``) is the right fix when we tackle the concurrency
        # follow-up; for now the cost (a duplicate GitHub review) is
        # vastly preferable to the previous failure mode (re-runs
        # silently lost forever).

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

        if not result:
            continue

        # Tag the agent-stored entries with the GitHub review id so the
        # webhook handler (``_handle_pr_review``) can recognise GitHub's
        # echo of our own post and skip the duplicate store. Without
        # this, every agent inline comment gets counted twice in
        # ``bud.code_review_comments``: once by the agent path, once
        # when GitHub fires ``pull_request_review`` back at us.
        review_id_raw = result.get("id") if isinstance(result, dict) else None
        if not isinstance(review_id_raw, int):
            logger.error(
                "github_review_id_missing",
                pr_number=pr.github_pr_number,
                bud_id=str(bud_id),
                result_keys=sorted(result.keys()) if isinstance(result, dict) else None,
            )
            continue

        await _tag_agent_review_id(db, org_id, bud_id, repo_name, review_id_raw)
        await db.flush()
        logger.info(
            "github_review_posted",
            pr_number=pr.github_pr_number,
            comment_count=len(matching),
            review_id=review_id_raw,
        )


async def _store_agent_comments_in_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    comments: list[dict[str, Any]],
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


async def _tag_agent_review_id(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    repo_name: str,
    review_id: int,
) -> None:
    """Stamp ``review_id`` onto agent-stored entries for ``repo_name``.

    Called from :func:`sync_review_comments_to_github` after
    ``create_pr_review`` returns. The webhook handler
    (``_handle_pr_review`` in ``github_webhook_handler``) uses the
    presence of this field to recognise GitHub's echo of the agent's
    own review and skip the duplicate inline / summary store that
    otherwise inflates the BUD's ``code_review_comments`` count.

    Only entries with ``source: "agent"`` AND matching ``repo`` are
    touched; existing ``review_id`` values are not overwritten (a re-run
    on the same repo shouldn't blast the prior correlation if for some
    reason the post step was already done).
    """
    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_id_for_update(bud_id)
    if not bud:
        return

    updated: list[dict[str, Any]] = []
    changed = False
    for c in bud.code_review_comments or []:
        is_agent_for_repo = (
            c.get("source") == "agent" and c.get("repo") == repo_name and not c.get("review_id")
        )
        if is_agent_for_repo:
            updated.append({**c, "review_id": review_id})
            changed = True
        else:
            updated.append(c)

    if changed:
        bud.code_review_comments = updated
        await db.flush()


def _map_to_github_comments(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
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

        entry: dict[str, Any] = {
            "path": file_path,
            "body": f"{prefix} {comment_body}",
        }
        if line and isinstance(line, int):
            entry["line"] = line

        gh_comments.append(entry)

    return gh_comments
