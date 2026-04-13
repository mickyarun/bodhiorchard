"""XP rules — pure constants and functions for level, streak, and unlock logic.

No database or async dependencies. Safe to import anywhere without side effects.
"""

from dataclasses import dataclass

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


# ─── Skill Points ─────────────────────────────

SKILL_POINTS_PER_XP = 1

# ─── Vehicle Unlock Costs ─────────────────────

VEHICLE_UNLOCKS: dict[str, int] = {
    "horse": 50,
}

# ─── House Tier Costs ─────────────────────────

HOUSE_TIER_COSTS: dict[int, int] = {
    1: 0,
    2: 0,
    3: 100,
}


def get_unlocked_items_for_level(level: int) -> UnlockedItems:
    """Return unlocked character/accessory IDs for a given level."""
    return UnlockedItems(
        characters=[k for k, v in CHARACTER_UNLOCKS.items() if v <= level],
        accessories=[k for k, v in ACCESSORY_UNLOCKS.items() if v <= level],
    )
