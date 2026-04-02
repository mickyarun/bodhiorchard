"""GitHub webhook event processing for PR lifecycle tracking.

Handles PR opened, closed/merged, synchronized, and review events.
Links PRs to BUDs via branch naming convention (bud-NNN/...).
Triggers auto-transitions when all impacted repos have PRs or all merge.
"""

import re
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pull_request import PRReviewStatus, PRState, PullRequest
from app.models.tracked_repository import TrackedRepository
from app.models.user import User
from app.repositories.pull_request import PullRequestRepository
from app.schemas.github import GitHubPullRequest, GitHubReview
from app.services.bud_timeline import record_event
from app.services.pr_auto_transition import (
    check_all_prs_merged,
    check_all_repos_have_prs,
    resolve_bud_from_branch,
)

logger = structlog.get_logger(__name__)

_BUD_BRANCH_RE = re.compile(r"bud-0*(\d+)/", re.IGNORECASE)


async def handle_github_event(
    org_id: uuid.UUID,
    repo: TrackedRepository,
    event_type: str,
    payload: dict,
    db: AsyncSession,
) -> None:
    """Dispatch a GitHub webhook event to the appropriate handler."""
    action = payload.get("action", "")

    if event_type == "pull_request":
        pr_data = GitHubPullRequest.model_validate(payload["pull_request"])
        if action == "opened":
            await _handle_pr_opened(org_id, repo, pr_data, db)
        elif action == "closed":
            await _handle_pr_closed(org_id, repo, pr_data, db)
        elif action == "synchronize":
            await _handle_pr_synchronize(org_id, pr_data, db)
    elif event_type == "pull_request_review" and action == "submitted":
        review = GitHubReview.model_validate(payload["review"])
        pr_data = GitHubPullRequest.model_validate(payload["pull_request"])
        await _handle_review_submitted(org_id, pr_data, review, db)


async def _handle_pr_opened(
    org_id: uuid.UUID,
    repo: TrackedRepository,
    pr_data: GitHubPullRequest,
    db: AsyncSession,
) -> None:
    """Create PR record and check if all impacted repos have PRs."""
    bud_id, bud = await resolve_bud_from_branch(db, org_id, pr_data.head.ref)

    pr_repo = PullRequestRepository(db, org_id=org_id)
    existing = await pr_repo.get_by_github_pr_id(pr_data.id)
    if existing:
        return  # Already tracked

    pr = PullRequest(
        org_id=org_id,
        bud_id=bud_id,
        repo_id=repo.id,
        github_pr_number=pr_data.number,
        github_pr_id=pr_data.id,
        github_repo_full_name=f"{repo.github_repo_full_name or ''}",
        title=pr_data.title,
        body=pr_data.body,
        html_url=pr_data.html_url,
        head_branch=pr_data.head.ref,
        base_branch=pr_data.base.ref,
        state=PRState.OPEN,
        author_github_login=pr_data.user.login,
    )
    db.add(pr)
    await db.flush()

    if bud:
        await record_event(
            db, org_id, bud.id, "pr_opened",
            detail={
                "pr_number": pr_data.number,
                "repo": repo.name,
                "html_url": pr_data.html_url,
            },
        )
        await check_all_repos_have_prs(db, org_id, bud)

    # Award XP for opening a PR
    author_user_id = await _resolve_github_user(db, org_id, pr_data.user.login)
    if author_user_id:
        try:
            from app.services.xp_service import award_xp

            await award_xp(
                db, user_id=author_user_id, org_id=org_id,
                xp_amount=15, source="pr_opened",
                source_ref=f"pr:{pr_data.id}",
            )
        except Exception:
            logger.warning("xp_award_failed_pr_opened", exc_info=True)

    await db.commit()
    logger.info(
        "pr_opened_tracked",
        pr_number=pr_data.number,
        bud_id=str(bud_id) if bud_id else None,
    )


async def _handle_pr_closed(
    org_id: uuid.UUID,
    repo: TrackedRepository,
    pr_data: GitHubPullRequest,
    db: AsyncSession,
) -> None:
    """Update PR state on close/merge. Check if all PRs merged."""
    pr_repo = PullRequestRepository(db, org_id=org_id)
    pr = await pr_repo.get_by_github_pr_id(pr_data.id)
    if not pr:
        return

    is_merged = pr_data.merged or False
    pr.state = PRState.MERGED if is_merged else PRState.CLOSED
    if is_merged and pr_data.merged_at:
        from datetime import datetime

        pr.merged_at = datetime.fromisoformat(pr_data.merged_at.replace("Z", "+00:00"))

    if pr.bud_id and is_merged:
        await record_event(
            db, org_id, pr.bud_id, "pr_merged",
            detail={
                "pr_number": pr_data.number,
                "repo": repo.name,
                "html_url": pr_data.html_url,
            },
        )
        await check_all_prs_merged(db, org_id, pr.bud_id)

    # Award XP for merging a PR (author gets credit)
    if is_merged:
        author_user_id = await _resolve_github_user(db, org_id, pr_data.user.login)
        if author_user_id:
            try:
                from app.services.xp_service import award_xp

                await award_xp(
                    db, user_id=author_user_id, org_id=org_id,
                    xp_amount=25, source="pr_merged",
                    source_ref=f"pr_merged:{pr_data.id}",
                )
            except Exception:
                logger.warning("xp_award_failed_pr_merged", exc_info=True)

    await db.commit()
    logger.info(
        "pr_closed_tracked",
        pr_number=pr_data.number,
        merged=is_merged,
    )


async def _handle_pr_synchronize(
    org_id: uuid.UUID,
    pr_data: GitHubPullRequest,
    db: AsyncSession,
) -> None:
    """Update PR record on push (force push, new commits)."""
    pr_repo = PullRequestRepository(db, org_id=org_id)
    pr = await pr_repo.get_by_github_pr_id(pr_data.id)
    if pr:
        pr.head_branch = pr_data.head.ref
        await db.commit()


async def _handle_review_submitted(
    org_id: uuid.UUID,
    pr_data: GitHubPullRequest,
    review: GitHubReview,
    db: AsyncSession,
) -> None:
    """Update PR review status from GitHub review."""
    pr_repo = PullRequestRepository(db, org_id=org_id)
    pr = await pr_repo.get_by_github_pr_id(pr_data.id)
    if not pr:
        return

    state_map = {
        "APPROVED": PRReviewStatus.APPROVED,
        "CHANGES_REQUESTED": PRReviewStatus.CHANGES_REQUESTED,
    }
    new_status = state_map.get(review.state.upper())
    if new_status:
        pr.review_status = new_status

        # Award XP to the reviewer
        reviewer_user_id = await _resolve_github_user(db, org_id, review.user.login)
        if reviewer_user_id:
            try:
                from app.services.xp_service import award_xp

                await award_xp(
                    db, user_id=reviewer_user_id, org_id=org_id,
                    xp_amount=20, source="review",
                    source_ref=f"review:{pr_data.id}:{review.user.login}",
                )
            except Exception:
                logger.warning("xp_award_failed_review", exc_info=True)

        await db.commit()


async def _resolve_github_user(
    db: AsyncSession,
    org_id: uuid.UUID,
    github_login: str,
) -> uuid.UUID | None:
    """Resolve a GitHub login to a user_id within the org."""
    if not github_login:
        return None
    stmt = (
        select(User.id)
        .where(User.github_username == github_login, User.org_id == org_id)
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

