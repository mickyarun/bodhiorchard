# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

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


async def find_buds_for_shas(
    db: AsyncSession,
    org_id: uuid.UUID,
    shas: list[str],
) -> dict[str, uuid.UUID]:
    """Batch-find which BUD each commit SHA belongs to.

    Returns a dict mapping ``sha \u2192 bud_id`` for all matched SHAs. Uses
    two bulk ``IN (...)`` queries instead of per-SHA round-trips:

    1. ``PullRequest.merge_commit_sha IN (...)`` \u2014 canonical post-merge SHA
    2. ``DevActivityLog.commit_sha IN (...)`` \u2014 fallback for merge-commit
       strategy where individual SHAs survive

    SHAs matched by strategy 1 take priority (strategy 2 only runs for
    SHAs not yet resolved).
    """
    if not shas:
        return {}

    result_map: dict[str, uuid.UUID] = {}

    # Strategy 1: bulk PullRequest.merge_commit_sha lookup
    pr_stmt = select(PullRequest.merge_commit_sha, PullRequest.bud_id).where(
        PullRequest.org_id == org_id,
        PullRequest.merge_commit_sha.in_(shas),
        PullRequest.bud_id.is_not(None),
    )
    pr_result = await db.execute(pr_stmt)
    for sha, bud_id in pr_result.all():
        if sha and bud_id:
            result_map[sha] = bud_id

    # Strategy 2: bulk DevActivityLog.commit_sha lookup for unmatched SHAs
    remaining = [s for s in shas if s not in result_map]
    if remaining:
        dev_stmt = (
            select(DevActivityLog.commit_sha, DevActivityLog.bud_id)
            .where(
                DevActivityLog.org_id == org_id,
                DevActivityLog.commit_sha.in_(remaining),
                DevActivityLog.bud_id.is_not(None),
            )
            .distinct()
        )
        dev_result = await db.execute(dev_stmt)
        for sha, bud_id in dev_result.all():
            if sha and bud_id and sha not in result_map:
                result_map[sha] = bud_id

    return result_map


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
    stmt = select(BUDTimelineEvent).where(
        BUDTimelineEvent.org_id == org_id,
        BUDTimelineEvent.bud_id == bud_id,
        BUDTimelineEvent.event_type == event_type,
    )
    result = await db.execute(stmt)
    for event in result.scalars():
        d = event.detail or {}
        if d.get("release_pr_number") == release_pr_number and d.get("repo_id") == str(repo_id):
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
    does a batch SHA lookup (2 SQL queries total regardless of commit count),
    and writes one ``merged_to_{stage}`` timeline event per matched BUD
    (idempotent on webhook re-delivery).

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

    # Batch SHA lookup \u2014 2 SQL queries total instead of 2N per-commit
    all_shas = [c.get("sha", "") for c in commits if c.get("sha")]
    sha_to_bud = await find_buds_for_shas(db, org_id, all_shas)

    # Bucket commits by owning BUD so each BUD gets a single event
    # carrying ALL its matched commits.
    matches: dict[uuid.UUID, list[dict[str, str]]] = {}
    for commit in commits:
        sha = commit.get("sha", "")
        bud_id = sha_to_bud.get(sha)
        if bud_id is None:
            continue
        commit_message = ""
        commit_obj = commit.get("commit") or {}
        if isinstance(commit_obj, dict):
            commit_message = (commit_obj.get("message") or "").split("\n", 1)[0][:200]
        matches.setdefault(bud_id, []).append(
            {"sha": sha, "message": commit_message},
        )

    # Write one event per BUD, idempotent on re-delivery.
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
    # shipped to production.
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

    Only fires when the BUD is currently in ``prod`` or ``uat`` status \u2014
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
    if not isinstance(impacted, list):
        return
    if not impacted:
        return

    impacted_repo_ids = {
        r.get("repo_id") for r in impacted if isinstance(r, dict) and r.get("repo_id")
    }
    if not impacted_repo_ids:
        return

    # Check which repos already have merged_to_prod events for this BUD
    stmt = select(BUDTimelineEvent).where(
        BUDTimelineEvent.org_id == org_id,
        BUDTimelineEvent.bud_id == bud_id,
        BUDTimelineEvent.event_type == "merged_to_prod",
    )
    result = await db.execute(stmt)
    prod_events = list(result.scalars())
    repos_with_prod = {e.detail.get("repo_id") for e in prod_events if e.detail}

    if not impacted_repo_ids.issubset(repos_with_prod):
        return  # Not all repos have shipped yet

    # All impacted repos have merged to prod \u2014 auto-close
    bud.status = BUDStatus.CLOSED

    # Record FeatureLearning (cycle time) — the manual PATCH handler calls
    # transition_feature_for_bud but the auto-close path was missing it.
    try:
        from app.services.feature_lifecycle import transition_feature_for_bud

        await transition_feature_for_bud(db, org_id, bud.bud_number, BUDStatus.CLOSED)
    except Exception:
        logger.warning("auto_close_feature_transition_failed", bud_id=str(bud_id), exc_info=True)

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

    # Post-closure side-effects: award contributor XP + trigger scan
    try:
        from app.services.bud_closure import on_bud_closed

        await on_bud_closed(db, org_id, bud)
    except Exception:
        logger.warning("auto_close_side_effects_failed", bud_id=str(bud_id), exc_info=True)

    logger.info(
        "bud_auto_closed_all_repos_in_prod",
        bud_id=str(bud_id),
        impacted_count=len(impacted_repo_ids),
    )
