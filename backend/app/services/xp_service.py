"""XP service — award, streak, level, and unlock logic.

All XP mutations go through award_xp() which handles dedup, level-up
detection, and WebSocket notification. Streak logic is in check_and_award_streak().
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.developer_xp import DeveloperXPRepository, XPEventRepository
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

    xp_awarded: int
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
    xp_amount: int,
    source: str,
    source_ref: str | None = None,
    multiplier: float = 1.0,
    metadata: dict | None = None,
) -> XPAwardResult | None:
    """Award XP to a developer. Handles dedup, level-up, and WebSocket publish.

    Returns None if deduped (source_ref already awarded). Otherwise returns
    XPAwardResult with old/new level and whether a level-up occurred.
    """
    from sqlalchemy.exc import IntegrityError

    xp_repo = DeveloperXPRepository(db, org_id=org_id)
    event_repo = XPEventRepository(db, org_id=org_id)

    # Dedup via source_ref (app-level check + DB unique constraint as safety net)
    if source_ref and await event_repo.has_source_ref(source_ref):
        logger.debug("xp_dedup_skip", source_ref=source_ref, user_id=str(user_id))
        return None

    effective_xp = max(0, int(xp_amount * multiplier))
    if effective_xp == 0:
        return None

    # Get or create aggregate row (locked for update)
    row = await xp_repo.get_or_create(user_id)
    old_level = row.level

    # Update aggregate
    row.total_xp += effective_xp
    new_level, new_name = compute_level(row.total_xp)
    row.level = new_level
    row.level_name = new_name

    # Record audit event — SAVEPOINT scopes the IntegrityError so it doesn't
    # roll back the caller's uncommitted work (DevActivityLog, PullRequest, etc.)
    try:
        async with db.begin_nested():
            await event_repo.create(
                user_id=user_id,
                xp_amount=effective_xp,
                source=source,
                source_ref=source_ref,
                multiplier=multiplier,
                metadata=metadata,
            )
    except IntegrityError:
        logger.debug("xp_dedup_integrity", source_ref=source_ref)
        return None

    level_changed = new_level != old_level
    result = XPAwardResult(
        xp_awarded=effective_xp,
        new_total=row.total_xp,
        old_level=old_level,
        new_level=new_level,
        level_changed=level_changed,
        new_level_name=new_name,
    )

    # Publish real-time notification
    publish(
        f"xp:{user_id}",
        {
            "event_type": "level_up" if level_changed else "xp_awarded",
            "xp_amount": effective_xp,
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

    event_repo = XPEventRepository(db, org_id=org_id)
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
                    user_id=user_id, xp_amount=effective_xp,
                    source="streak", source_ref=source_ref, multiplier=mult,
                )
        except IntegrityError:
            logger.debug("xp_streak_dedup", source_ref=source_ref)

        if new_level != old_level:
            publish(f"xp:{user_id}", {
                "event_type": "level_up", "xp_amount": effective_xp,
                "source": "streak", "new_total": row.total_xp,
                "level": new_level, "level_name": new_name,
                "level_changed": True, "streak_count": row.streak_count,
            })

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

    tasks_stmt = (
        select(BUDAgentTask)
        .where(BUDAgentTask.bud_id == bud_id)
    )
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
        xp_amount=bonus_xp,
        source="quality_bonus",
        source_ref=f"quality:{user_id}:{bud_id}",
        metadata={"effectiveness_score": score},
    )

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
