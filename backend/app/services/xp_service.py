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

"""XP service — award, streak, level, and unlock logic.

All XP mutations go through award_xp() which handles dedup, level-up
detection, and WebSocket notification. Streak logic is in check_and_award_streak().
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.developer_xp import RewardType
from app.repositories.developer_xp import DeveloperXPRepository, RewardEventRepository
from app.services.event_bus import publish
from app.services.xp_rules import (
    UnlockedItems,
    compute_level,
    get_unlocked_items_for_level,
    streak_multiplier,
    xp_for_next_level,
)

logger = structlog.get_logger(__name__)

# Re-export for callers that import from xp_service
__all__ = [
    "award_xp",
    "check_and_award_streak",
    "award_quality_bonus",
    "get_unlocked_items",
    "compute_level",
    "xp_for_next_level",
    "UnlockedItems",
    "XPAwardResult",
]


# ─── XP Award Result ───────────────────────────


@dataclass
class XPAwardResult:
    """Returned by award_xp() to inform the caller of state changes."""

    amount_awarded: int
    new_total: int
    old_level: int
    new_level: int
    level_changed: bool
    new_level_name: str


# ─── Core Functions ─────────────────────────────


async def award_xp(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    amount: float,
    source: str,
    source_ref: str | None = None,
    multiplier: float = 1.0,
    metadata: dict[str, Any] | None = None,
    bud_id: uuid.UUID | None = None,
) -> XPAwardResult | None:
    """Award XP to a developer. Handles dedup, level-up, and WebSocket publish.

    ``amount`` accepts floats so stage-promotion awards can split a fixed
    pool (e.g. 25 XP) among contributors without losing precision in the
    audit trail. ``RewardEvent.amount`` stores the exact fractional value
    (``Numeric(10,2)``); the aggregate ``DeveloperXP.total_xp`` is an
    integer so it's rounded once at increment time. Pass ``bud_id`` when
    the award is tied to a specific BUD so per-BUD earnings can be queried
    without parsing ``source_ref``.

    Returns None if deduped (source_ref already awarded). Otherwise returns
    XPAwardResult with old/new level and whether a level-up occurred.
    """
    from sqlalchemy.exc import IntegrityError

    xp_repo = DeveloperXPRepository(db, org_id=org_id)
    event_repo = RewardEventRepository(db, org_id=org_id)

    # Dedup via source_ref (app-level check + DB unique constraint as safety net)
    if source_ref and await event_repo.has_source_ref(source_ref):
        logger.debug("xp_dedup_skip", source_ref=source_ref, user_id=str(user_id))
        return None

    effective_xp = round(max(0.0, amount * multiplier), 2)
    if effective_xp == 0:
        return None

    # Get or create aggregate row (locked for update)
    row = await xp_repo.get_or_create(user_id)
    old_level = row.level

    # Aggregate is an integer column — round once on increment, keep the
    # precise fractional amount on the audit row.
    row.total_xp += round(effective_xp)
    new_level, new_name = compute_level(row.total_xp)
    row.level = new_level
    row.level_name = new_name

    # Record audit event — SAVEPOINT scopes the IntegrityError so it doesn't
    # roll back the caller's uncommitted work (DevActivityLog, PullRequest, etc.)
    try:
        async with db.begin_nested():
            await event_repo.create(
                user_id=user_id,
                reward_type=RewardType.XP,
                amount=effective_xp,
                source=source,
                source_ref=source_ref,
                multiplier=multiplier,
                metadata=metadata,
                bud_id=bud_id,
            )
    except IntegrityError:
        logger.debug("xp_dedup_integrity", source_ref=source_ref)
        return None

    level_changed = new_level != old_level
    result = XPAwardResult(
        amount_awarded=round(effective_xp),
        new_total=row.total_xp,
        old_level=old_level,
        new_level=new_level,
        level_changed=level_changed,
        new_level_name=new_name,
    )

    # Publish real-time notification. ``amount`` is rounded to int for the
    # toast so a split like 8.33 doesn't render as ``+8.33 XP`` — the audit
    # row keeps the precise fractional value, but the UI signal stays clean.
    publish(
        f"xp:{user_id}",
        {
            "event_type": "level_up" if level_changed else "xp_awarded",
            "type": RewardType.XP.value,
            "amount": round(effective_xp),
            "source": source,
            "new_total": row.total_xp,
            "level": new_level,
            "level_name": new_name,
            "level_changed": level_changed,
            "streak_count": row.streak_count,
        },
    )

    if level_changed:
        logger.info(
            "xp_level_up",
            user_id=str(user_id),
            old_level=old_level,
            new_level=new_level,
            total_xp=row.total_xp,
        )

    return result


async def check_and_award_streak(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> int:
    """Check if today is a new active day. Award streak XP if so.

    Returns the current streak_count (0 if no change).
    """
    xp_repo = DeveloperXPRepository(db, org_id=org_id)
    row = await xp_repo.get_or_create(user_id)

    today = datetime.now(UTC).date()

    # Already counted today
    if row.last_active_date == today:
        return row.streak_count

    yesterday = today - timedelta(days=1)

    if row.last_active_date == yesterday:
        # Streak continues
        row.streak_count += 1
    else:
        # Streak broken (or first activity)
        row.streak_count = 1

    row.last_active_date = today
    row.streak_best = max(row.streak_best, row.streak_count)

    # Award streak XP directly on the already-locked row (avoids double FOR UPDATE)
    mult = streak_multiplier(row.streak_count)
    effective_xp = max(0, int(10 * mult))
    source_ref = f"streak:{user_id}:{today.isoformat()}"

    event_repo = RewardEventRepository(db, org_id=org_id)
    if not await event_repo.has_source_ref(source_ref):
        old_level = row.level
        row.total_xp += effective_xp
        new_level, new_name = compute_level(row.total_xp)
        row.level = new_level
        row.level_name = new_name

        from sqlalchemy.exc import IntegrityError

        # Flush streak mutations first so they survive a nested rollback
        await db.flush()

        try:
            async with db.begin_nested():
                await event_repo.create(
                    user_id=user_id,
                    reward_type=RewardType.XP,
                    amount=effective_xp,
                    source="streak",
                    source_ref=source_ref,
                    multiplier=mult,
                )
        except IntegrityError:
            logger.debug("xp_streak_dedup", source_ref=source_ref)

        if new_level != old_level:
            publish(
                f"xp:{user_id}",
                {
                    "event_type": "level_up",
                    "type": RewardType.XP.value,
                    "amount": effective_xp,
                    "source": "streak",
                    "new_total": row.total_xp,
                    "level": new_level,
                    "level_name": new_name,
                    "level_changed": True,
                    "streak_count": row.streak_count,
                },
            )

    # SP milestones for streak achievements
    if row.streak_count in (14, 30):
        try:
            from app.services.sp_rules import SP_STREAK_14, SP_STREAK_30
            from app.services.sp_service import award_sp

            sp_amount = SP_STREAK_30 if row.streak_count == 30 else SP_STREAK_14
            await award_sp(
                db,
                user_id=user_id,
                org_id=org_id,
                amount=sp_amount,
                source="sp_streak",
                source_ref=f"sp_streak_{row.streak_count}:{user_id}:{today.isoformat()}",
            )
        except Exception:
            logger.warning("sp_streak_award_failed", exc_info=True)

    return row.streak_count


async def award_quality_bonus(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
) -> int:
    """Award quality bonus XP based on BUD effectiveness metrics.

    Returns the XP awarded (0-30).
    """
    from sqlalchemy import select

    from app.models.bud_agent_task import BUDAgentTask
    from app.models.dev_activity import DevActivityLog
    from app.services.dev_stats import calculate_effectiveness

    # Fetch activities for this BUD
    activities_stmt = (
        select(DevActivityLog)
        .where(DevActivityLog.bud_id == bud_id)
        .order_by(DevActivityLog.created_at.desc())
        .limit(100)
    )
    activities_result = await db.execute(activities_stmt)
    activities = list(activities_result.scalars().all())

    tasks_stmt = select(BUDAgentTask).where(BUDAgentTask.bud_id == bud_id)
    tasks_result = await db.execute(tasks_stmt)
    tasks = list(tasks_result.scalars().all())

    if not activities:
        return 0

    stats = calculate_effectiveness(activities, tasks)
    score = stats.get("score", 0)

    # Map effectiveness score (0-100) to bonus XP (0-30)
    bonus_xp = int(score * 0.3)
    if bonus_xp <= 0:
        return 0

    await award_xp(
        db,
        user_id=user_id,
        org_id=org_id,
        amount=bonus_xp,
        source="quality_bonus",
        source_ref=f"quality:{user_id}:{bud_id}",
        metadata={"effectiveness_score": score},
    )

    # SP bonus for high-quality work (score > 80)
    if score > 80:
        try:
            from app.services.sp_rules import SP_DEV_QUALITY_HIGH
            from app.services.sp_service import award_sp

            await award_sp(
                db,
                user_id=user_id,
                org_id=org_id,
                amount=SP_DEV_QUALITY_HIGH,
                source="sp_quality",
                source_ref=f"sp_quality:{user_id}:{bud_id}",
            )
        except Exception:
            logger.warning("sp_award_failed_quality", exc_info=True)

    return bonus_xp


async def get_unlocked_items(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> UnlockedItems:
    """Return unlocked characters/accessories for a user based on their level."""
    xp_repo = DeveloperXPRepository(db, org_id=org_id)
    row = await xp_repo.get_by_user(user_id)
    level = row.level if row else 1
    return get_unlocked_items_for_level(level)
