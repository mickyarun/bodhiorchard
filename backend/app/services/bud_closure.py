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

"""Side-effects that fire when a BUD reaches closed status.

Called from both the manual PATCH handler (bud.py) and the automatic
closure path (_maybe_auto_close_bud in release_detection.py). Centralizes
two post-closure actions:

1. **Award XP to all contributors** — every user who committed code or
   authored a PR for this BUD receives contributor XP. The assignee's
   50 XP award is handled upstream (bud.py) and is NOT duplicated here.
2. **Trigger a background repo scan** — impacted repos are re-scanned so
   features and skills are updated to reflect the shipped work.

Both actions are fire-and-forget: failures are logged but never block
the caller. XP awards are idempotent via ``source_ref`` dedup.
"""

import asyncio
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.dev_activity import DevActivityLog
from app.models.pull_request import PullRequest
from app.services.scan.runner import ScanAlreadyActiveError, start_scan

logger = structlog.get_logger(__name__)


async def on_bud_closed(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    actor_id: uuid.UUID | None = None,
    actor_name: str | None = None,
) -> None:
    """Run post-closure side-effects for a BUD.

    Safe to call multiple times — XP awards are deduped by ``source_ref``
    and the scan is a fresh incremental run.
    """
    await _award_contributor_xp(db, org_id, bud)
    await _award_bud_shipped_sp(db, org_id, bud)
    _trigger_impacted_repo_scan(org_id, bud)


async def _award_contributor_xp(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> None:
    """Award XP to every user who contributed to this BUD.

    Collects distinct user_ids from DevActivityLog commits and PullRequest
    authors. Excludes the assignee (they already receive 50 XP via the
    upstream ``bud_completed`` award in bud.py). Each contributor gets
    25 XP with a dedup key that prevents double-awarding on re-closure.
    """
    from app.services.xp_service import award_xp

    contributor_ids: set[uuid.UUID] = set()

    # Source 1: commit authors from dev activity
    dev_stmt = (
        select(DevActivityLog.user_id)
        .where(
            DevActivityLog.org_id == org_id,
            DevActivityLog.bud_id == bud.id,
            DevActivityLog.user_id.is_not(None),
        )
        .distinct()
    )
    dev_result = await db.execute(dev_stmt)
    for (uid,) in dev_result.all():
        if uid:
            contributor_ids.add(uid)

    # Source 2: PR authors
    pr_stmt = (
        select(PullRequest.author_user_id)
        .where(
            PullRequest.org_id == org_id,
            PullRequest.bud_id == bud.id,
            PullRequest.author_user_id.is_not(None),
        )
        .distinct()
    )
    pr_result = await db.execute(pr_stmt)
    for (uid,) in pr_result.all():
        if uid:
            contributor_ids.add(uid)

    # Exclude the assignee — they already get 50 XP from the upstream award
    if bud.assignee_id:
        contributor_ids.discard(bud.assignee_id)

    if not contributor_ids:
        return

    awarded = 0
    for uid in contributor_ids:
        try:
            result = await award_xp(
                db,
                user_id=uid,
                org_id=org_id,
                amount=25,
                source="bud_contributor",
                source_ref=f"bud_contrib:{bud.bud_number}:{uid}",
            )
            if result is not None:
                awarded += 1
        except Exception:
            logger.warning(
                "contributor_xp_award_failed",
                user_id=str(uid),
                bud_id=str(bud.id),
                exc_info=True,
            )

    if awarded:
        logger.info(
            "bud_contributor_xp_awarded",
            bud_id=str(bud.id),
            bud_number=bud.bud_number,
            contributors=awarded,
            total_found=len(contributor_ids),
        )


def _trigger_impacted_repo_scan(
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> None:
    """Trigger a background scan for the BUD's impacted repos.

    Uses its own DB session so the caller returns immediately. Runs an
    incremental scan (not full rescan) to update features and skills
    for the repos that shipped new code.
    """
    impacted = bud.impacted_repos
    if not isinstance(impacted, list) or not impacted:
        return

    repo_ids: list[str] = [
        str(rid) for r in impacted if isinstance(r, dict) and (rid := r.get("repo_id"))
    ]
    if not repo_ids:
        return

    task = asyncio.create_task(
        _bg_scan(org_id, repo_ids, bud.bud_number),
        name=f"bg_scan_bud_{bud.bud_number}",
    )
    # _bg_scan wraps its body in try/except, so success / known failures
    # are already logged. The callback exists only to retrieve any
    # exception that escapes _bg_scan itself (otherwise asyncio prints a
    # warning about an unretrieved exception at GC time).
    task.add_done_callback(_log_bg_scan_exception)


def _log_bg_scan_exception(task: asyncio.Task[None]) -> None:
    """Drain the task's exception (if any) and log it.

    Calling ``task.exception()`` marks the exception as retrieved,
    which prevents the asyncio "Task exception was never retrieved"
    warning at GC time.
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.warning("bud_closure_bg_scan_unhandled", exc_info=exc)


async def _bg_scan(
    org_id: uuid.UUID,
    repo_ids: list[str],
    bud_number: int,
) -> None:
    """Background task: kick off a scan for the impacted repos."""
    try:
        repo_uuids: list[uuid.UUID] = []
        for rid in repo_ids:
            try:
                repo_uuids.append(uuid.UUID(rid))
            except ValueError:
                logger.warning("bud_closure_invalid_repo_id", bud_number=bud_number, repo_id=rid)
        if not repo_uuids:
            return

        scan_id = await start_scan(org_id=org_id, repo_ids=repo_uuids)
        logger.info(
            "bud_closure_scan_started",
            bud_number=bud_number,
            repos_scanned=len(repo_uuids),
            scan_id=str(scan_id),
        )
    except ScanAlreadyActiveError as exc:
        logger.info(
            "bud_closure_scan_skipped_already_active",
            bud_number=bud_number,
            active_scan_id=str(exc.scan_id),
        )
    except Exception:
        logger.warning(
            "bud_closure_scan_failed",
            bud_number=bud_number,
            exc_info=True,
        )


async def _award_bud_shipped_sp(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> None:
    """Award role-based SP to the BUD assignee when a BUD ships to PROD."""
    if not bud.assignee_id:
        return

    try:
        from app.services.sp_rules import BUD_SHIPPED_SP
        from app.services.sp_service import award_sp, get_user_role

        role = await get_user_role(db, bud.assignee_id, org_id)
        sp_amount = BUD_SHIPPED_SP.get(role)
        if sp_amount:
            await award_sp(
                db,
                user_id=bud.assignee_id,
                org_id=org_id,
                amount=sp_amount,
                source="sp_bud_shipped",
                source_ref=f"sp_bud_shipped:{bud.bud_number}:{bud.assignee_id}",
            )
    except Exception:
        logger.warning("sp_award_failed_bud_shipped", exc_info=True)
