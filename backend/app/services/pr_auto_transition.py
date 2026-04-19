# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""BUD auto-transition logic triggered by PR events.

Centralizes the "when should BUD auto-advance?" state machine:
- All impacted repos have PRs → development → code_review
- All PRs merged → code_review → testing

Reusable by webhook handlers, manual sync, or cron jobs.
"""

import re
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.repositories.bud import BUDRepository
from app.repositories.pull_request import PullRequestRepository
from app.services.bud_timeline import record_event

logger = structlog.get_logger(__name__)

_BUD_BRANCH_RE = re.compile(r"bud-0*(\d+)/", re.IGNORECASE)


async def resolve_bud_from_branch(
    db: AsyncSession,
    org_id: uuid.UUID,
    branch: str,
) -> tuple[uuid.UUID | None, BUDDocument | None]:
    """Extract BUD number from branch name and find the BUD."""
    match = _BUD_BRANCH_RE.match(branch)
    if not match:
        return None, None

    bud_number = int(match.group(1))
    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_number(bud_number)
    return (bud.id, bud) if bud else (None, None)


async def check_all_repos_have_prs(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> None:
    """Auto-transition to code_review if all impacted repos have PRs."""
    if bud.status != BUDStatus.DEVELOPMENT:
        return

    impacted = bud.impacted_repos or []
    if not impacted:
        return

    pr_repo = PullRequestRepository(db, org_id=org_id)
    repo_ids_with_prs = await pr_repo.get_repo_ids_with_prs(bud.id)

    impacted_ids = {str(r.get("repo_id")) for r in impacted if r.get("repo_id")}
    if not impacted_ids:
        return

    if impacted_ids.issubset(repo_ids_with_prs):
        # Auto-populate confirmed_repos so code review agent has repo paths
        from app.repositories.tracked_repository import TrackedRepoRepository

        tr_repo = TrackedRepoRepository(db, org_id=org_id)
        repo_triples = await tr_repo.get_active_id_path_name()
        confirmed = [
            {"repo_path": path, "repo_name": name}
            for rid, path, name in repo_triples
            if str(rid) in impacted_ids
        ]
        meta = dict(bud.metadata_ or {})
        meta["confirmed_repos"] = confirmed
        bud.metadata_ = meta

        bud.status = BUDStatus.CODE_REVIEW

        await record_event(
            db,
            org_id,
            bud.id,
            "status_change",
            detail={"from": "development", "to": "code_review", "auto": True},
        )

        from app.services.bud_agent_trigger import create_agent_task_for_stage

        await create_agent_task_for_stage(bud, "code_review", org_id, db)
        # Estimation deferred — triggers after code review completes (agent_result_handlers)
        logger.info("auto_transition_to_code_review", bud_id=str(bud.id))


async def check_all_prs_merged(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
) -> None:
    """Auto-transition to testing if every impacted repo has a merged PR.

    Uses the same per-repo priority collapse as ``get_pr_status_summary``
    (OPEN > MERGED > CLOSED), so that historical closed-without-merging
    PRs from earlier development iterations don't block the transition.
    A BUD with 14 closed PRs and 1 merged PR on the same repo should
    auto-advance just like a clean single-PR BUD.

    Code review correctness is delegated entirely to GitHub PR reviews +
    merges — merging a PR is the human signal that the change has been
    reviewed and approved. No LLM gate between code_review and testing.
    """
    from app.services.bud_code_review_status import get_pr_status_summary

    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if not bud or bud.status != BUDStatus.CODE_REVIEW:
        return

    repo_statuses = await get_pr_status_summary(db, org_id, bud)
    if not repo_statuses:
        return  # no impacted repos — override is the only path forward
    if not all(r["pr_state"] == "merged" for r in repo_statuses):
        return  # at least one impacted repo hasn't landed yet

    bud.status = BUDStatus.TESTING

    await record_event(
        db,
        org_id,
        bud.id,
        "all_prs_merged",
        detail={"from": "code_review", "to": "testing", "auto": True},
    )
    await record_event(
        db,
        org_id,
        bud.id,
        "status_change",
        detail={"from": "code_review", "to": "testing", "auto": True},
    )

    from app.services.bud_agent_trigger import create_agent_task_for_stage

    await create_agent_task_for_stage(bud, "testing", org_id, db, force=True)

    try:
        from app.services.bud_estimation import estimate_bud_dates

        await estimate_bud_dates(db, org_id, bud, trigger="prs_merged")
    except Exception:
        logger.warning("estimation_failed_after_prs_merged", bud_id=str(bud_id))
    logger.info("auto_transition_to_testing", bud_id=str(bud_id))
