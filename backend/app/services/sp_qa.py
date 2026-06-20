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

"""QA Skill-Point rules, settled at outcome time (not at bug creation).

Two entry points:

* :func:`award_qa_sp_on_close` — at BUD close: reward the QA who filed more
  than the complexity bug budget, and reward the testing-phase QA for a
  clean exit (reduced if they skipped/overrode test cases).
* :func:`award_qa_sp_on_bug_status` — on a bug status change: reward the
  reporter when a production bug they raised is confirmed (closed), and
  penalise them when a bug they raised is rejected as a false positive.

All awards are role-gated to ``qa``, deduped on ``source_ref``, and
best-effort: a failure is logged and never blocks the caller.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.bug import Bug, BugStatus, BugType
from app.repositories.bud_timeline import BUDTimelineRepository
from app.repositories.bug import BugRepository
from app.services.org_settings import get_bug_threshold
from app.services.sp_rules import (
    SP_QA_BUG_REJECTED,
    SP_QA_BUGS_OVER_THRESHOLD,
    SP_QA_PROD_BUG_FOUND,
    SP_QA_TESTS_COMPLETE,
    SP_QA_TESTS_OVERRIDDEN,
)
from app.services.sp_service import award_sp, get_user_role, penalize_sp

logger = structlog.get_logger(__name__)

_TESTING_PHASE = "testing"


async def _reward_over_threshold_reporters(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    org_config: dict[str, Any] | None,
) -> None:
    """Credit QA reporters when testing bugs exceeded the complexity budget."""
    bug_repo = BugRepository(db, org_id=org_id)
    count = await bug_repo.count_valid_testing_bugs_for_bud(bud.id)
    threshold = get_bug_threshold(org_config, bud.complexity)
    if count <= threshold:
        return

    for reporter_id in await bug_repo.distinct_testing_reporters_for_bud(bud.id):
        if await get_user_role(db, reporter_id, org_id) != "qa":
            continue
        await award_sp(
            db,
            user_id=reporter_id,
            org_id=org_id,
            amount=SP_QA_BUGS_OVER_THRESHOLD,
            source="sp_qa_over_threshold",
            source_ref=f"sp_qa_threshold:{bud.bud_number}:{reporter_id}",
        )


async def _reward_clean_testing_exit(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> None:
    """Credit the testing-phase QA, reduced if they skipped/overrode cases."""
    assignment = await BUDTimelineRepository(db, org_id=org_id).latest_assignee_for_phase(
        bud.id, _TESTING_PHASE
    )
    if assignment is None:
        return
    qa_id = assignment[0]
    if await get_user_role(db, qa_id, org_id) != "qa":
        return

    overridden = await BUDTimelineRepository(db, org_id=org_id).has_qa_skip_override(bud.id)
    amount = SP_QA_TESTS_OVERRIDDEN if overridden else SP_QA_TESTS_COMPLETE
    await award_sp(
        db,
        user_id=qa_id,
        org_id=org_id,
        amount=amount,
        source="sp_qa_tests",
        source_ref=f"sp_qa_tests:{bud.bud_number}:{qa_id}",
    )


async def award_qa_sp_on_close(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    *,
    org_config: dict[str, Any] | None,
) -> None:
    """Run the close-time QA rules for a BUD. Each leg is best-effort."""
    try:
        await _reward_over_threshold_reporters(db, org_id, bud, org_config)
    except Exception:
        logger.warning("sp_qa_over_threshold_failed", bud_number=bud.bud_number, exc_info=True)

    try:
        await _reward_clean_testing_exit(db, org_id, bud)
    except Exception:
        logger.warning("sp_qa_tests_failed", bud_number=bud.bud_number, exc_info=True)


async def award_qa_sp_on_bug_status(
    db: AsyncSession,
    bug: Bug,
    new_status: BugStatus,
) -> None:
    """Settle QA SP on a bug status change (production-closed reward / reject penalty).

    Gated to ``qa`` reporters and deduped per bug, so re-saving the same
    status never double-credits. Best-effort — never blocks the bug update.
    """
    try:
        if new_status not in (BugStatus.CLOSED, BugStatus.REJECTED):
            return
        if await get_user_role(db, bug.reporter_id, bug.org_id) != "qa":
            return

        if new_status == BugStatus.REJECTED:
            await penalize_sp(
                db,
                user_id=bug.reporter_id,
                org_id=bug.org_id,
                amount=abs(SP_QA_BUG_REJECTED),
                source="sp_qa_rejected",
                source_ref=f"sp_qa_rejected:{bug.id}",
            )
        elif bug.bug_type == BugType.PRODUCTION:
            await award_sp(
                db,
                user_id=bug.reporter_id,
                org_id=bug.org_id,
                amount=SP_QA_PROD_BUG_FOUND,
                source="sp_qa_prod_bug",
                # Reuse the legacy ``sp_qa_prod:{bug_id}`` key (the retired
                # create-time reward used it) so a production bug that already
                # paid its reporter under the old code can't be double-credited
                # when it later closes under this rule.
                source_ref=f"sp_qa_prod:{bug.id}",
            )
    except Exception:
        logger.warning("sp_qa_bug_status_failed", bug_id=str(bug.id), exc_info=True)
