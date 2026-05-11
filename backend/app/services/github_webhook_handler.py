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

"""GitHub webhook event processing for PR lifecycle tracking.

Handles PR opened, closed/merged, synchronized, and review events.
Links PRs to BUDs via branch naming convention (bud-NNN/...).
Triggers auto-transitions when all impacted repos have PRs or all merge.
"""

import re
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pull_request import PRReviewStatus, PRState, PullRequest
from app.models.tracked_repository import SetupPrState, TrackedRepository
from app.repositories.bud import BUDRepository
from app.repositories.pull_request import PullRequestRepository
from app.repositories.user import UserRepository
from app.schemas.github import GitHubComment, GitHubPullRequest, GitHubReview
from app.services.bud_timeline import record_event
from app.services.job_queue import JOB_PR_MERGE_UPDATE, create_job
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
                amount=15,
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
    is_merged = pr_data.merged or False

    # Setup-PR state lives on ``tracked_repository``, not ``pull_requests``.
    # Run this branch *before* the pull-requests lookup so adopted setup PRs
    # — which may not have a ``pull_requests`` row when the App opened the
    # PR from a different environment than the one currently receiving the
    # webhook — still flip from "open" to "merged"/"closed" on close. The
    # wider PR-tracking work below depends on a ``pull_requests`` row and
    # stays correctly gated.
    if repo.setup_pr_number == pr_data.number:
        repo.setup_pr_state = SetupPrState.MERGED if is_merged else SetupPrState.CLOSED
        logger.info(
            "setup_pr_state_updated",
            repo=repo.name,
            pr_number=pr_data.number,
            merged=is_merged,
        )

    pr_repo = PullRequestRepository(db, org_id=org_id)
    pr = await pr_repo.get_by_github_pr_id(pr_data.id)
    if not pr:
        # Persist the setup_pr_state flip before bailing on PR-tracking;
        # the unified ``await db.commit()`` at the bottom of this function
        # is unreachable on the early-return path.
        await db.commit()
        return

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
                    amount=25,
                    source="pr_merged",
                    source_ref=f"pr_merged:{pr_data.id}",
                )
            except Exception:
                logger.warning("xp_award_failed_pr_merged", exc_info=True)

            # SP award for PR merged (role-based)
            try:
                from app.services.sp_rules import SP_DEV_PR_MERGED
                from app.services.sp_service import award_sp, get_user_role

                role = await get_user_role(db, author_user_id, org_id)
                if role == "developer":
                    await award_sp(
                        db,
                        user_id=author_user_id,
                        org_id=org_id,
                        amount=SP_DEV_PR_MERGED,
                        source="sp_pr_merged",
                        source_ref=f"sp_pr_merged:{pr_data.id}",
                    )
            except Exception:
                logger.warning("sp_award_failed_pr_merged", exc_info=True)

    # Release-stage detection: if this PR was merged into a configured
    # uat / main branch, walk its commits and record merged_to_{stage}
    # events on every BUD whose work is included. Runs for ANY merged PR,
    # not just BUD-branch PRs \u2014 a release PR (e.g. develop \u2192 release/uat)
    # has no bud-NNN head branch but is exactly what we want to detect.
    if is_merged:
        await _maybe_detect_release_promotion(org_id, repo, pr_data, pr, db)

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

    # Feature-reconcile fan-out (purely additive). On a successful
    # merge, enqueue a cluster-scoped feature-reconcile job so the
    # Features tab tracks merged work without waiting for the next
    # scheduled scan. Wrapped in try/except so a queueing failure
    # never breaks the existing PR-tracking flow above.
    if is_merged and pr_data.merge_commit_sha:
        _enqueue_pr_merge_feature_reconcile(org_id, repo, pr_data)


def _enqueue_pr_merge_feature_reconcile(
    org_id: uuid.UUID,
    repo: TrackedRepository,
    pr_data: GitHubPullRequest,
) -> None:
    """Enqueue the PR-merge feature-reconcile job. Failures are logged, never raised."""
    try:
        merge_head = pr_data.merge_commit_sha or pr_data.head.sha
        create_job(
            JOB_PR_MERGE_UPDATE,
            payload={
                "org_id": str(org_id),
                "repo_id": str(repo.id),
                "pr_number": pr_data.number,
                "base_sha": pr_data.base.sha,
                "head_sha": merge_head,
                "full_name": repo.github_repo_full_name or "",
            },
            user_id=None,
        )
    except Exception:
        logger.warning(
            "pr_merge_feature_reconcile_enqueue_failed",
            repo_id=str(repo.id),
            pr_number=pr_data.number,
            exc_info=True,
        )


async def _maybe_detect_release_promotion(
    org_id: uuid.UUID,
    repo: TrackedRepository,
    pr_data: GitHubPullRequest,
    pr: PullRequest,
    db: AsyncSession,
) -> None:
    """Record release-stage events when a PR merges into a stage branch.

    Two paths, chosen automatically:

    **Fast path** \u2014 the PR already has ``bud_id`` (BUD-branch PR merging
    directly into a stage branch, e.g. ``bud-001/... \u2192 release/uat``).
    Records ``merged_to_{stage}`` directly from the PR's metadata.
    Zero GitHub API calls.

    **SHA-walk path** \u2014 the PR has no ``bud_id`` (release PR carrying
    multiple BUDs, e.g. ``develop \u2192 main``). Fetches the PR's commits
    via GitHub API and batch-matches SHAs to discover which BUDs are
    included. One API call + 2 SQL queries.

    Failures are logged but never break the parent webhook handler \u2014
    detection is observational and must not block PR state updates.
    """
    from app.services.release_detection import ReleaseStage, detect_release_promotion

    base_ref = pr_data.base.ref
    if not base_ref:
        return

    stage: ReleaseStage | None = None
    from app.utils.branch_matching import branch_matches

    if repo.uat_branch and branch_matches(base_ref, repo.uat_branch):
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
        if pr.bud_id:
            # Fast path: BUD-branch PR merged directly into a stage branch.
            # We already know the BUD \u2014 skip the GitHub API call entirely.
            await _record_release_event_for_bud(
                db,
                org_id,
                pr.bud_id,
                repo,
                pr_data,
                stage,
            )
        else:
            # SHA-walk path: release PR carrying multiple BUDs.
            await detect_release_promotion(db, org_id, repo, pr_data, stage)
    except Exception:
        logger.warning(
            "release_detection_failed",
            stage=stage,
            pr_number=pr_data.number,
            repo=repo.name,
            exc_info=True,
        )


async def _record_release_event_for_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    repo: TrackedRepository,
    pr_data: GitHubPullRequest,
    stage: str,
) -> None:
    """Fast-path: record a merged_to_{stage} event for a known BUD.

    Called when a BUD-branch PR (which already carries ``bud_id``) merges
    directly into a stage branch. Skips the GitHub API commit-walk and
    SHA matching entirely.
    """
    from app.services.release_detection import _event_already_recorded, _maybe_auto_close_bud

    already = await _event_already_recorded(
        db,
        org_id,
        bud_id,
        stage,
        pr_data.number,
        repo.id,  # type: ignore[arg-type]
    )
    if already:
        return

    await record_event(
        db,
        org_id,
        bud_id,
        f"merged_to_{stage}",
        detail={
            "release_pr_number": pr_data.number,
            "release_pr_html_url": pr_data.html_url,
            "release_pr_title": pr_data.title,
            "release_pr_author": pr_data.user.login,
            "repo_id": str(repo.id),
            "repo_name": repo.name,
            "merged_at": pr_data.merged_at,
            "matched_commits": [],
        },
    )

    from app.services.event_bus import publish as _publish

    _publish(
        f"bud:{bud_id}:activity",
        {"event_type": f"merged_to_{stage}", "release_pr_number": pr_data.number},
    )

    if stage == "prod":
        await _maybe_auto_close_bud(db, org_id, bud_id)

    logger.info(
        "release_event_fast_path",
        stage=stage,
        bud_id=str(bud_id),
        pr_number=pr_data.number,
        repo=repo.name,
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
                    amount=20,
                    source="review",
                    source_ref=f"review:{pr_data.id}:{review.user.login}",
                )
            except Exception:
                logger.warning("xp_award_failed_review", exc_info=True)

            # SP award for code review (role-based)
            try:
                from app.services.sp_rules import REVIEW_SP
                from app.services.sp_service import award_sp, get_user_role

                role = await get_user_role(db, reviewer_user_id, org_id)
                sp_amount = REVIEW_SP.get(role)
                if sp_amount:
                    await award_sp(
                        db,
                        user_id=reviewer_user_id,
                        org_id=org_id,
                        amount=sp_amount,
                        source="sp_review",
                        source_ref=f"sp_review:{pr_data.id}:{review.user.login}",
                    )
            except Exception:
                logger.warning("sp_award_failed_review", exc_info=True)

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
    pr_repo = PullRequestRepository(db, org_id=org_id)
    pr = await pr_repo.get_by_repo_and_number(repo.github_repo_full_name, pr_number)
    if not pr or not pr.bud_id:
        return

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
    return await UserRepository(db).get_id_by_github_login(org_id, github_login)
