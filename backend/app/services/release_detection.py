"""Release-stage detection: which BUDs landed in a release PR.

When a release PR (e.g. ``develop \u2192 release/uat`` or ``develop \u2192 main``)
is merged, this service walks the PR's commits and records a
``merged_to_uat`` / ``merged_to_prod`` timeline event on every BUD whose
work is included.

The lookup keys off two SHA sources, in priority order:

1. ``PullRequest.merge_commit_sha`` \u2014 the SHA written to ``develop`` when
   that BUD's branch PR was merged. Set on every merge strategy
   (merge / squash / rebase) so it's the canonical signal.
2. ``DevActivityLog.commit_sha`` \u2014 individual commits captured by the
   Claude Code hook. Only matchable when ``develop`` was created with a
   merge commit (preserving the original SHAs); a fallback for legacy
   data and the merge-commit case.

Detection is observational only \u2014 it does NOT auto-advance ``BUDStatus``.
The org-level ``bud_stages.uat_enabled`` toggle gates the UAT path; Prod
is always enabled.

Idempotency: re-delivered webhooks must not double-write events. The
dedupe key is the quad ``(bud_id, stage, release_pr_number, repo_id)``,
checked by querying existing ``merged_to_{stage}`` events for this BUD
and matching against the same fields stored in their ``detail`` JSON.
"""

import uuid
from typing import Literal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDTimelineEvent
from app.models.dev_activity import DevActivityLog
from app.models.organization import Organization
from app.models.pull_request import PullRequest
from app.models.tracked_repository import TrackedRepository
from app.schemas.github import GitHubPullRequest
from app.services.bud_timeline import record_event
from app.services.event_bus import publish
from app.services.github_app_auth import get_installation_token
from app.services.github_client import GitHubClient

logger = structlog.get_logger(__name__)

ReleaseStage = Literal["uat", "prod"]


async def find_bud_for_sha(
    db: AsyncSession,
    org_id: uuid.UUID,
    sha: str,
) -> uuid.UUID | None:
    """Find which BUD a commit SHA belongs to.

    Two-step lookup, returns on the first match:

    1. ``PullRequest.merge_commit_sha == sha`` \u2014 a previously merged
       BUD-branch PR landed this exact SHA on develop. Works for all merge
       strategies because GitHub's webhook gives us the post-merge SHA.
    2. ``DevActivityLog.commit_sha == sha`` \u2014 the commit was authored
       directly by a developer working on a bud branch (matches the
       merge-commit strategy where individual SHAs survive the merge).

    Returns ``None`` if no BUD owns this SHA \u2014 expected for unrelated
    commits in a release PR.
    """
    if not sha:
        return None

    # Strategy 1: previously merged BUD-branch PR.
    pr_stmt = (
        select(PullRequest.bud_id)
        .where(
            PullRequest.org_id == org_id,
            PullRequest.merge_commit_sha == sha,
            PullRequest.bud_id.is_not(None),
        )
        .limit(1)
    )
    result = await db.execute(pr_stmt)
    bud_id = result.scalar_one_or_none()
    if bud_id is not None:
        return bud_id

    # Strategy 2: original dev commit captured by Claude Code hook.
    dev_stmt = (
        select(DevActivityLog.bud_id)
        .where(
            DevActivityLog.org_id == org_id,
            DevActivityLog.commit_sha == sha,
            DevActivityLog.bud_id.is_not(None),
        )
        .limit(1)
    )
    result = await db.execute(dev_stmt)
    return result.scalar_one_or_none()


async def _event_already_recorded(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    stage: ReleaseStage,
    release_pr_number: int,
    repo_id: uuid.UUID,
) -> bool:
    """Idempotency guard: has this exact promotion already been recorded?

    Looks up existing ``merged_to_{stage}`` events for this BUD and
    matches the dedupe quad in their ``detail`` JSON. Cheap because each
    BUD has very few release events (one per stage per repo, typically).
    """
    event_type = f"merged_to_{stage}"
    stmt = (
        select(BUDTimelineEvent)
        .where(
            BUDTimelineEvent.org_id == org_id,
            BUDTimelineEvent.bud_id == bud_id,
            BUDTimelineEvent.event_type == event_type,
        )
    )
    result = await db.execute(stmt)
    for event in result.scalars():
        d = event.detail or {}
        if (
            d.get("release_pr_number") == release_pr_number
            and d.get("repo_id") == str(repo_id)
        ):
            return True
    return False


async def detect_release_promotion(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo: TrackedRepository,
    pr_data: GitHubPullRequest,
    stage: ReleaseStage,
) -> int:
    """Walk a merged release PR's commits and record per-BUD events.

    Called from the GitHub webhook handler after the existing BUD-branch
    detection runs. Fetches the release PR's commits via the GitHub API,
    fans out each commit through ``find_bud_for_sha``, and writes one
    ``merged_to_{stage}`` timeline event per matched BUD (idempotent on
    webhook re-delivery).

    Args:
        db: Async DB session.
        org_id: Owning organization.
        repo: Tracked repository the release PR belongs to.
        pr_data: The release PR webhook payload.
        stage: ``"uat"`` or ``"prod"``.

    Returns:
        Number of distinct BUDs newly promoted to this stage. Zero if
        all matched events were already recorded (re-delivery).
    """
    if not repo.github_repo_full_name:
        logger.warning(
            "release_detection_skipped_no_github_repo",
            repo_id=str(repo.id),
            stage=stage,
        )
        return 0

    org = await db.get(Organization, org_id)
    if org is None:
        return 0
    token = await get_installation_token(org)
    if not token:
        logger.warning(
            "release_detection_skipped_no_github_token",
            org_id=str(org_id),
            stage=stage,
        )
        return 0

    client = GitHubClient(token)
    commits = await client.get_pr_commits(
        repo.github_repo_full_name,
        pr_data.number,
    )
    if not commits:
        return 0

    # First pass: bucket commits by owning BUD so each BUD gets a single
    # event carrying ALL its matched commits, not just the first one. The
    # UI needs the full list to show "these N commits from this BUD shipped
    # in that release" \u2014 critical for spotting dropped or cherry-picked work.
    matches: dict[uuid.UUID, list[dict[str, str]]] = {}
    for commit in commits:
        sha = commit.get("sha", "")
        bud_id = await find_bud_for_sha(db, org_id, sha)
        if bud_id is None:
            continue
        commit_message = ""
        commit_obj = commit.get("commit") or {}
        if isinstance(commit_obj, dict):
            commit_message = (commit_obj.get("message") or "").split("\n", 1)[0][:200]
        matches.setdefault(bud_id, []).append(
            {"sha": sha, "message": commit_message},
        )

    # Second pass: write one event per BUD, idempotent on re-delivery.
    new_event_count = 0
    for bud_id, bud_commits in matches.items():
        already = await _event_already_recorded(
            db,
            org_id,
            bud_id,
            stage,
            pr_data.number,
            repo.id,
        )
        if already:
            continue

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
                "matched_commits": bud_commits,
            },
        )
        publish(
            f"bud:{bud_id}:activity",
            {
                "event_type": f"merged_to_{stage}",
                "release_pr_number": pr_data.number,
            },
        )
        new_event_count += 1

    # For prod merges: auto-close the BUD when ALL impacted repos have
    # shipped to production. This mirrors the CODE_REVIEW → TESTING
    # auto-transition pattern (all repos merged → advance) but for the
    # final lifecycle step.
    if stage == "prod" and new_event_count:
        for bud_id in matches:
            await _maybe_auto_close_bud(db, org_id, bud_id)

    if new_event_count:
        logger.info(
            "release_promotion_detected",
            stage=stage,
            release_pr_number=pr_data.number,
            repo=repo.name,
            new_buds=new_event_count,
            commits_walked=len(commits),
        )
    return new_event_count


async def _maybe_auto_close_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
) -> None:
    """Auto-close a BUD if all impacted repos have merged_to_prod events.

    Only fires when the BUD is currently in ``prod`` or ``uat`` status —
    if it's already ``closed`` or still in ``testing``, this is a no-op.
    Records a ``status_change`` timeline event with ``auto: true`` so the
    timeline shows it was system-driven.
    """
    from app.models.bud import BUDStatus
    from app.repositories.bud import BUDRepository

    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        return
    if bud.status not in (BUDStatus.UAT, BUDStatus.PROD):
        return

    impacted = bud.impacted_repos or []
    if not impacted:
        return

    impacted_repo_ids = {
        r.get("repo_id") for r in impacted if r.get("repo_id")
    }
    if not impacted_repo_ids:
        return

    # Check which repos already have merged_to_prod events for this BUD
    stmt = (
        select(BUDTimelineEvent)
        .where(
            BUDTimelineEvent.org_id == org_id,
            BUDTimelineEvent.bud_id == bud_id,
            BUDTimelineEvent.event_type == "merged_to_prod",
        )
    )
    result = await db.execute(stmt)
    prod_events = list(result.scalars())
    repos_with_prod = {
        e.detail.get("repo_id")
        for e in prod_events
        if e.detail
    }

    if not impacted_repo_ids.issubset(repos_with_prod):
        return  # Not all repos have shipped yet

    # All impacted repos have merged to prod — auto-close
    bud.status = BUDStatus.CLOSED

    await record_event(
        db,
        org_id,
        bud_id,
        "status_change",
        detail={
            "from": "prod",
            "to": "closed",
            "auto": True,
            "reason": "All impacted repos merged to production",
        },
    )
    publish(
        f"bud:{bud_id}:activity",
        {"event_type": "status_change", "to": "closed"},
    )
    logger.info(
        "bud_auto_closed_all_repos_in_prod",
        bud_id=str(bud_id),
        impacted_count=len(impacted_repo_ids),
    )
