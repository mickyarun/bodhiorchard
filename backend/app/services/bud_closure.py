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
the post-closure rewards and learning hooks:

1. **Award XP to all contributors** — every user who committed code or
   authored a PR for this BUD receives contributor XP. The assignee's
   50 XP award is handled upstream (bud.py) and is NOT duplicated here.
2. **Award role-based SP to the assignee** for shipping a BUD to prod.
3. **Compute BUD learning metrics** (only on CLOSED transitions).
4. **Spawn the post-close Learning Agent** when the BUD opted in via
   ``auto_generate_phases.closed``.

Repo scans are NOT triggered from here — they are owned by the PR-merge
GitHub webhook (``api/v1/github_webhook.py`` → ``services/scan/pr_merge_update.py``)
which gates on the repo's ``main_branch``. Closing a BUD on its own does
not advance any tracked SHA, so firing a scan from this path was both
unnecessary work and a source of false-positive feature deactivations.

Linked-features ``in_progress → done`` transition runs upstream in
``bud.py`` via ``feature_lifecycle.transition_feature_for_bud`` on every
status change, independent of this module.

Failures are logged but never block the caller. XP and SP awards are
idempotent via ``source_ref`` dedup.
"""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.dev_activity import DevActivityLog
from app.models.pull_request import PullRequest
from app.services.bud_agent_trigger import (
    create_agent_task_for_stage,
    should_auto_generate_phase,
)
from app.services.bud_metrics import compute_and_persist as compute_bud_metrics

logger = structlog.get_logger(__name__)


async def on_bud_closed(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    actor_id: uuid.UUID | None = None,
    actor_name: str | None = None,
) -> None:
    """Run post-closure side-effects for a BUD.

    Safe to call multiple times — XP and SP awards are deduped by
    ``source_ref``, and ``compute_bud_metrics`` is a no-op when the
    FeatureLearning row already carries a ``metrics`` envelope.

    Note that this hook fires on PROD *and* CLOSED transitions today
    (see ``bud.py``'s ``_completed`` gate). XP and SP are correct to
    fire at PROD; learning-metrics and the post-close Learning Agent
    only fire at CLOSED so the full lifecycle is captured (PROD→CLOSED
    happens later via auto-close).
    """
    await _award_contributor_xp(db, org_id, bud)
    await _award_bud_shipped_sp(db, org_id, bud)

    if bud.status == BUDStatus.CLOSED:
        try:
            await compute_bud_metrics(db, org_id, bud)
        except Exception:
            logger.warning(
                "bud_metrics_compute_failed",
                bud_id=str(bud.id),
                bud_number=bud.bud_number,
                exc_info=True,
            )

        # Spawn the post-close Learning Agent if the BUD opted in via
        # auto_generate_phases.closed. Defaults off so the External-LLM
        # contract holds — orgs that bring their own AI tooling won't
        # see us spawn LLM work on close unless they explicitly enable it.
        if should_auto_generate_phase(bud.auto_generate_phases, "closed"):
            try:
                await create_agent_task_for_stage(
                    bud,
                    "closed",
                    org_id,
                    db,
                    triggered_by=actor_id,
                )
            except Exception:
                logger.warning(
                    "learning_agent_trigger_failed",
                    bud_id=str(bud.id),
                    bud_number=bud.bud_number,
                    exc_info=True,
                )


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
