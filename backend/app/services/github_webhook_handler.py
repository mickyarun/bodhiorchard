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
from app.schemas.github import GitHubComment, GitHubPullRequest, GitHubReview
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
    elif event_type in ("issue_comment", "pull_request_review_comment"):
        if action == "created":
            comment = GitHubComment.model_validate(payload["comment"])
            pr_number = payload.get("pull_request", {}).get("number") or payload.get(
                "issue", {}
            ).get("number")
            if pr_number:
                await _handle_pr_comment(org_id, repo, pr_number, comment, db)


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
            db,
            org_id,
            bud.id,
            "pr_opened",
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
                db,
                user_id=author_user_id,
                org_id=org_id,
                xp_amount=15,
                source="pr_opened",
                source_ref=f"pr:{pr_data.id}",
            )
        except Exception:
            logger.warning("xp_award_failed_pr_opened", exc_info=True)

    await db.commit()

    # Push update to frontend so BUD detail refreshes
    if bud_id:
        from app.services.event_bus import publish

        publish(
            f"bud:{bud_id}:activity",
            {"event_type": "pr_opened", "pr_number": pr_data.number},
        )

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

    # Capture the post-merge SHA so downstream release-stage detection
    # can match this BUD's commits to release PRs (e.g. develop \u2192 uat),
    # regardless of whether the merge strategy was merge / squash / rebase.
    if is_merged and pr_data.merge_commit_sha:
        pr.merge_commit_sha = pr_data.merge_commit_sha

    if pr.bud_id and is_merged:
        await record_event(
            db,
            org_id,
            pr.bud_id,
            "pr_merged",
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
                    db,
                    user_id=author_user_id,
                    org_id=org_id,
                    xp_amount=25,
                    source="pr_merged",
                    source_ref=f"pr_merged:{pr_data.id}",
                )
            except Exception:
                logger.warning("xp_award_failed_pr_merged", exc_info=True)

    # Release-stage detection: if this PR was merged into a configured
    # uat / main branch, walk its commits and record merged_to_{stage}
    # events on every BUD whose work is included. Runs for ANY merged PR,
    # not just BUD-branch PRs \u2014 a release PR (e.g. develop \u2192 release/uat)
    # has no bud-NNN head branch but is exactly what we want to detect.
    if is_merged:
        await _maybe_detect_release_promotion(org_id, repo, pr_data, db)

    await db.commit()

    if pr.bud_id:
        from app.services.event_bus import publish

        event = "pr_merged" if is_merged else "pr_closed"
        publish(
            f"bud:{pr.bud_id}:activity",
            {"event_type": event, "pr_number": pr_data.number},
        )

    logger.info(
        "pr_closed_tracked",
        pr_number=pr_data.number,
        merged=is_merged,
    )


def _branch_matches(ref: str, pattern: str) -> bool:
    """Check if a branch ref matches a configured pattern.

    Supports exact match (``release/uat``) and ``fnmatch``-style wildcards
    (``release*`` matches ``release/uat``, ``release/v2.1``). Patterns
    without glob characters fall back to simple equality — no regex.
    """
    if "*" in pattern or "?" in pattern or "[" in pattern:
        from fnmatch import fnmatch

        return fnmatch(ref, pattern)
    return ref == pattern


async def _maybe_detect_release_promotion(
    org_id: uuid.UUID,
    repo: TrackedRepository,
    pr_data: GitHubPullRequest,
    db: AsyncSession,
) -> None:
    """Run release-stage detection if the PR's base branch is a release target.

    Compares ``pr_data.base.ref`` against ``repo.uat_branch`` (gated by the
    org-level ``bud_stages.uat_enabled`` toggle) and ``repo.main_branch``.
    On match, fans out via ``release_detection.detect_release_promotion``.
    Failures are logged but never break the parent webhook handler \u2014
    detection is observational and must not block PR state updates.
    """
    from app.services.release_detection import ReleaseStage, detect_release_promotion

    base_ref = pr_data.base.ref
    if not base_ref:
        return

    stage: ReleaseStage | None = None
    if repo.uat_branch and _branch_matches(base_ref, repo.uat_branch):
        from app.models.organization import Organization
        from app.services.org_settings import is_uat_enabled

        org = await db.get(Organization, org_id)
        if org is not None and is_uat_enabled(org.config):
            stage = "uat"
    elif repo.main_branch and base_ref == repo.main_branch:
        stage = "prod"

    if stage is None:
        return

    try:
        await detect_release_promotion(db, org_id, repo, pr_data, stage)
    except Exception:
        logger.warning(
            "release_detection_failed",
            stage=stage,
            pr_number=pr_data.number,
            repo=repo.name,
            exc_info=True,
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

    # Update review status for approval/changes_requested
    state_map = {
        "APPROVED": PRReviewStatus.APPROVED,
        "CHANGES_REQUESTED": PRReviewStatus.CHANGES_REQUESTED,
    }
    new_status = state_map.get(review.state.upper())
    if new_status:
        pr.review_status = new_status

    # Fetch individual inline comments from GitHub API, store in dedicated column
    if pr.bud_id:
        try:
            await _fetch_and_store_review_comments(
                db,
                org_id,
                pr,
                pr_data,
                review,
            )
        except Exception:
            logger.warning(
                "fetch_review_comments_failed",
                review_id=review.id,
                pr_number=pr_data.number,
            )

    # Award XP to the reviewer
    if new_status:
        reviewer_user_id = await _resolve_github_user(
            db,
            org_id,
            review.user.login,
        )
        if reviewer_user_id:
            try:
                from app.services.xp_service import award_xp

                await award_xp(
                    db,
                    user_id=reviewer_user_id,
                    org_id=org_id,
                    xp_amount=20,
                    source="review",
                    source_ref=f"review:{pr_data.id}:{review.user.login}",
                )
            except Exception:
                logger.warning("xp_award_failed_review", exc_info=True)

    await db.commit()

    if pr.bud_id:
        from app.services.event_bus import publish

        publish(
            f"bud:{pr.bud_id}:activity",
            {"event_type": "review_submitted", "state": review.state},
        )


async def _fetch_and_store_review_comments(
    db: AsyncSession,
    org_id: uuid.UUID,
    pr: PullRequest,
    pr_data: GitHubPullRequest,
    review: GitHubReview,
) -> None:
    """Fetch inline comments for a review from GitHub API, store in BUD."""
    from app.models.organization import Organization
    from app.repositories.bud import BUDRepository
    from app.services.github_client import GitHubClient
    from app.services.github_pr_sync import get_installation_token

    org = await db.get(Organization, org_id)
    if not org:
        return
    token = await get_installation_token(org)
    if not token:
        return

    client = GitHubClient(token)
    gh_comments = await client.get_review_comments(
        pr.github_repo_full_name,
        pr_data.number,
        review.id,
    )

    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_id_for_update(pr.bud_id)
    if not bud:
        return

    existing = list(bud.code_review_comments or [])
    existing_ids = {c.get("github_comment_id") for c in existing if c.get("github_comment_id")}
    repo_name = (pr.github_repo_full_name or "").split("/")[-1]

    # Add review body as summary entry
    if review.body and review.body.strip() and review.id not in existing_ids:
        existing.append(
            {
                "github_comment_id": review.id,
                "review_id": review.id,
                "repo": repo_name,
                "file": "",
                "line": 0,
                "body": review.body[:2000],
                "author": review.user.login,
                "html_url": review.html_url or "",
                "created_at": "",
                "is_summary": True,
            }
        )

    # Add each inline comment
    for c in gh_comments:
        cid = c.get("id")
        if cid in existing_ids:
            continue
        existing.append(
            {
                "github_comment_id": cid,
                "review_id": review.id,
                "repo": repo_name,
                "file": c.get("path", ""),
                "line": c.get("line") or c.get("original_line") or 0,
                "body": (c.get("body") or "")[:2000],
                "author": c.get("user", {}).get("login", ""),
                "html_url": c.get("html_url", ""),
                "created_at": c.get("created_at", ""),
                "is_summary": False,
            }
        )

    bud.code_review_comments = existing
    await db.flush()

    logger.info(
        "review_comments_stored",
        bud_id=str(pr.bud_id),
        review_id=review.id,
        inline_count=len(gh_comments),
        total_stored=len(existing),
    )


async def _handle_pr_comment(
    org_id: uuid.UUID,
    repo: TrackedRepository,
    pr_number: int,
    comment: GitHubComment,
    db: AsyncSession,
) -> None:
    """Store a PR comment (issue_comment or review_comment) in the BUD."""
    stmt = (
        select(PullRequest)
        .where(
            PullRequest.org_id == org_id,
            PullRequest.github_pr_number == pr_number,
            PullRequest.github_repo_full_name == repo.github_repo_full_name,
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    pr = result.scalar_one_or_none()
    if not pr or not pr.bud_id:
        return

    from app.repositories.bud import BUDRepository

    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_id_for_update(pr.bud_id)
    if not bud:
        return

    existing = list(bud.code_review_comments or [])
    existing_ids = {c.get("github_comment_id") for c in existing if c.get("github_comment_id")}
    if comment.id in existing_ids:
        return

    repo_name = (repo.github_repo_full_name or "").split("/")[-1]
    existing.append(
        {
            "github_comment_id": comment.id,
            "repo": repo_name,
            "file": comment.path or "",
            "line": comment.line or 0,
            "body": comment.body[:2000],
            "author": comment.user.login,
            "html_url": comment.html_url,
            "created_at": comment.created_at,
            "is_summary": False,
        }
    )
    bud.code_review_comments = existing
    # Dedup guard above may leave FOR UPDATE lock — commit releases it
    await db.commit()

    logger.info(
        "pr_comment_stored",
        bud_id=str(pr.bud_id),
        pr_number=pr_number,
        author=comment.user.login,
    )

    try:
        from app.services.event_bus import publish

        publish(
            f"bud:{pr.bud_id}:activity",
            {"event_type": "pr_comment", "pr_number": pr_number},
        )
    except Exception:
        logger.warning("event_bus_publish_failed", bud_id=str(pr.bud_id))


async def _resolve_github_user(
    db: AsyncSession,
    org_id: uuid.UUID,
    github_login: str,
) -> uuid.UUID | None:
    """Resolve a GitHub login to a user_id within the org."""
    if not github_login:
        return None
    from app.models.user import OrgToUser

    stmt = (
        select(User.id)
        .join(OrgToUser, OrgToUser.user_id == User.id)
        .where(User.github_username == github_login, OrgToUser.org_id == org_id)
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
