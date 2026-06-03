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

"""Skill Point (SP) service — award, penalize, and query SP.

SP is a scarce, role-based currency. Unlike XP (free from activity), SP
rewards specific quality outcomes and penalises failures. Each award is
deduped via source_ref to prevent double-counting.
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bug import Bug, BugType
from app.models.developer_xp import RewardType
from app.models.user import User
from app.repositories.bud import BUDRepository
from app.repositories.bud_feature_link import BUDFeatureLinkRepository
from app.repositories.bug import BugRepository
from app.repositories.developer_xp import DeveloperXPRepository, RewardEventRepository
from app.repositories.user import UserRepository
from app.services.event_bus import publish
from app.services.sp_rules import (
    SP_DEV_BUG_PRODUCTION,
    SP_DEV_BUG_TESTING,
    SP_QA_BUGS_BATCH,
    SP_QA_BUGS_BATCH_SIZE,
    SP_QA_PROD_BUG_FOUND,
)

logger = structlog.get_logger(__name__)


async def award_sp(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    amount: float,
    source: str,
    source_ref: str | None = None,
) -> float | None:
    """Award SP to a user. Returns new balance, or None if deduped.

    - Dedup via source_ref (same pattern as XP events)
    - SP cannot go below 0 (floor)
    - Publishes real-time update via WebSocket
    """
    if amount == 0:
        return None

    # Dedup check
    if source_ref:
        event_repo = RewardEventRepository(db, org_id=org_id)
        if await event_repo.has_source_ref(source_ref):
            logger.debug("sp_dedup_skip", source_ref=source_ref, user_id=str(user_id))
            return None

    xp_repo = DeveloperXPRepository(db, org_id=org_id)
    row = await xp_repo.get_or_create(user_id)

    old_sp = float(row.skill_points)
    new_sp = max(0.0, old_sp + amount)
    row.skill_points = round(new_sp, 2)

    # Record the reward event (shared audit trail with XP, distinguished by type)
    if source_ref:
        from sqlalchemy.exc import IntegrityError

        try:
            async with db.begin_nested():
                await RewardEventRepository(db, org_id=org_id).create(
                    user_id=user_id,
                    reward_type=RewardType.SP,
                    amount=amount,
                    source=source,
                    source_ref=source_ref,
                    multiplier=1.0,
                    metadata={"sp_balance": new_sp},
                )
        except IntegrityError:
            # Restore balance — the ORM mutation happened before the savepoint
            row.skill_points = round(old_sp, 2)
            logger.debug("sp_dedup_integrity", source_ref=source_ref)
            return None

    logger.info(
        "sp_awarded",
        user_id=str(user_id),
        amount=amount,
        source=source,
        old_sp=old_sp,
        new_sp=new_sp,
    )

    # Real-time notification — shape mirrors award_xp so the frontend handler
    # can discriminate on `type` without separate branches per publisher.
    publish(
        f"xp:{user_id}",
        {
            "event_type": "sp_awarded",
            "type": RewardType.SP.value,
            "amount": amount,
            "source": source,
            "skill_points": new_sp,
        },
    )

    return new_sp


async def penalize_sp(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    amount: float,
    source: str,
    source_ref: str | None = None,
) -> float | None:
    """Deduct SP from a user. Amount should be positive (will be negated).

    SP is floored at 0 — cannot go negative.
    """
    return await award_sp(
        db,
        user_id=user_id,
        org_id=org_id,
        amount=-abs(amount),
        source=source,
        source_ref=source_ref,
    )


async def get_user_role(
    db: AsyncSession,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> str:
    """Resolve a user's role within an org. Returns role string or 'developer' as default."""
    role = await UserRepository(db).get_role(user_id, org_id)
    return role.value if role else "developer"


async def award_for_bug_created(
    db: AsyncSession,
    reporter: User,
    bug: Bug,
) -> None:
    """Apply the SP economy side-effects of a newly created bug.

    Three legs, all best-effort (any failure is logged and swallowed so a
    transient SP error never blocks the bug create response):

    1. **Developer penalty.** Find whose dev work caused the bug:
       - If ``bug.bud_id`` is set, penalise that BUD's assignee.
       - Else if ``bug.feature_id`` is set (the production-bug path),
         resolve the most recently-linked BUD for the Feature via
         :meth:`BUDFeatureLinkRepository.most_recent_bud_id_for_feature`
         and penalise its assignee. This is a heuristic — a future
         PR-to-file-path index could refine it — but it captures "who
         most recently changed this feature" without new schema. See
         :mod:`app.services.sp_rules` for the documented payer rule.
       - Amount: :data:`SP_DEV_BUG_PRODUCTION` for production bugs,
         :data:`SP_DEV_BUG_TESTING` otherwise.

    2. **QA reporter reward.** Only if the reporter's role is ``qa``:
       - Production bug → :data:`SP_QA_PROD_BUG_FOUND` (per-bug).
       - Testing bug → :data:`SP_QA_BUGS_BATCH` every
         :data:`SP_QA_BUGS_BATCH_SIZE` bugs (1-in-N batch reward).
    """
    # Best-effort by design: SP attribution is a side-effect of bug
    # creation, never load-bearing. Swallowing here keeps a transient
    # SP failure from blocking the bug create response.
    try:
        await _penalise_dev_for_bug(db, reporter.org_id, bug)
        await _reward_qa_reporter_for_bug(db, reporter, bug)
    except Exception:
        logger.warning(
            "sp_bug_award_failed",
            bug_id=str(bug.id),
            reporter_id=str(reporter.id),
            bug_type=bug.bug_type.value,
            exc_info=True,
        )


async def _penalise_dev_for_bug(
    db: AsyncSession,
    org_id: uuid.UUID,
    bug: Bug,
) -> None:
    """Resolve who owns the bug-causing work and dock their SP."""
    target_bud_id = bug.bud_id
    if target_bud_id is None and bug.feature_id is not None:
        link_repo = BUDFeatureLinkRepository(db, org_id=org_id)
        target_bud_id = await link_repo.most_recent_bud_id_for_feature(bug.feature_id)

    if target_bud_id is None:
        return

    bud_repo = BUDRepository(db, org_id=org_id)
    linked_bud = await bud_repo.get_by_id(target_bud_id)
    if not linked_bud or not linked_bud.assignee_id:
        return

    penalty = SP_DEV_BUG_PRODUCTION if bug.bug_type == BugType.PRODUCTION else SP_DEV_BUG_TESTING
    await penalize_sp(
        db,
        user_id=linked_bud.assignee_id,
        org_id=org_id,
        amount=abs(penalty),
        source="sp_bug_penalty",
        source_ref=f"sp_bug_dev:{bug.id}",
    )


async def _reward_qa_reporter_for_bug(
    db: AsyncSession,
    reporter: User,
    bug: Bug,
) -> None:
    """Award SP to the QA reporter, either per-bug (prod) or batched (testing)."""
    reporter_role = await get_user_role(db, reporter.id, reporter.org_id)
    if reporter_role != "qa":
        return

    if bug.bug_type == BugType.PRODUCTION:
        await award_sp(
            db,
            user_id=reporter.id,
            org_id=reporter.org_id,
            amount=SP_QA_PROD_BUG_FOUND,
            source="sp_qa_prod_bug",
            source_ref=f"sp_qa_prod:{bug.id}",
        )
        return

    # Testing bug — batch reward (every Nth bug)
    bug_repo = BugRepository(db, org_id=reporter.org_id)
    total = await bug_repo.count_testing_bugs_by_reporter(reporter.id)
    if total > 0 and total % SP_QA_BUGS_BATCH_SIZE == 0:
        batch_num = total // SP_QA_BUGS_BATCH_SIZE
        await award_sp(
            db,
            user_id=reporter.id,
            org_id=reporter.org_id,
            amount=SP_QA_BUGS_BATCH,
            source="sp_qa_bug_batch",
            source_ref=f"sp_qa_batch:{reporter.id}:{batch_num}",
        )
