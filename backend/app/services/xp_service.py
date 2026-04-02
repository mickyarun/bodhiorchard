"""XP service — award, streak, level, and unlock logic.

All XP mutations go through award_xp() which handles dedup, level-up
detection, and WebSocket notification. Streak logic is in check_and_award_streak().
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.developer_xp import DeveloperXPRepository, XPEventRepository
from app.services.event_bus import publish

logger = structlog.get_logger(__name__)

# ─── Level Thresholds ───────────────────────────

LEVELS: list[tuple[int, int, str]] = [
    (1, 0,    "seedling"),
    (2, 100,  "sprout"),
    (3, 500,  "sapling"),
    (4, 1500, "tree"),
    (5, 5000, "ancient_oak"),
]


def compute_level(total_xp: int) -> tuple[int, str]:
    """Pure function: XP → (level_number, level_name)."""
    result_level, result_name = 1, "seedling"
    for level, threshold, name in LEVELS:
        if total_xp >= threshold:
            result_level, result_name = level, name
    return result_level, result_name


def xp_for_next_level(total_xp: int) -> tuple[int, int]:
    """Return (xp_remaining, next_threshold). (0, 0) if max level."""
    for _, threshold, _ in LEVELS:
        if total_xp < threshold:
            return threshold - total_xp, threshold
    return 0, 0


# ─── Streak Multiplier ─────────────────────────

def streak_multiplier(streak_days: int) -> float:
    """Multiplier for daily streak XP based on consecutive active days."""
    if streak_days >= 30:
        return 2.5
    if streak_days >= 14:
        return 2.0
    if streak_days >= 7:
        return 1.5
    return 1.0


# ─── Character / Accessory Unlock Rules ────────

CHARACTER_UNLOCKS: dict[str, int] = {
    "barbarian": 1,
    "knight": 1,
    "mage": 2,
    "ranger": 3,
    "rogue": 4,
    "rogue_hooded": 5,
}

ACCESSORY_UNLOCKS: dict[str, int] = {
    "sword": 1,
    "mug": 1,
    "axe": 2,
    "dagger": 2,
    "staff": 3,
    "wand": 3,
    "bow": 4,
    "shield": 5,
}


@dataclass
class UnlockedItems:
    """Characters and accessories available at a given level."""

    characters: list[str]
    accessories: list[str]


def get_unlocked_items_for_level(level: int) -> UnlockedItems:
    """Return unlocked character/accessory IDs for a given level."""
    return UnlockedItems(
        characters=[k for k, v in CHARACTER_UNLOCKS.items() if v <= level],
        accessories=[k for k, v in ACCESSORY_UNLOCKS.items() if v <= level],
    )


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
    xp_repo = DeveloperXPRepository(db, org_id=org_id)
    event_repo = XPEventRepository(db, org_id=org_id)

    # Dedup via source_ref
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

    # Record audit event
    await event_repo.create(
        user_id=user_id,
        xp_amount=effective_xp,
        source=source,
        source_ref=source_ref,
        multiplier=multiplier,
        metadata=metadata,
    )

    await db.flush()

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

    today = date.today()

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

    # Award streak XP with multiplier
    mult = streak_multiplier(row.streak_count)
    await award_xp(
        db,
        user_id=user_id,
        org_id=org_id,
        xp_amount=10,
        source="streak",
        source_ref=f"streak:{today.isoformat()}",
        multiplier=mult,
    )

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
        source_ref=f"quality:{bud_id}",
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
