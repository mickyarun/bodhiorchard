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

"""XP rules — pure constants and functions for level, streak, and unlock logic.

No database or async dependencies. Safe to import anywhere without side effects.
"""

from dataclasses import dataclass

# ─── Level Thresholds ───────────────────────────

LEVELS: list[tuple[int, int, str]] = [
    (1, 0, "seedling"),
    (2, 100, "sprout"),
    (3, 500, "sapling"),
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
    "mage": 1,
    "knight": 3,
    "ranger": 3,
    "rogue": 4,
    "rogue_hooded": 5,
}

ACCESSORY_UNLOCKS: dict[str, int] = {
    "sword": 2,
    "mug": 2,
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


# ─── Vehicle Unlock Costs ─────────────────────

VEHICLE_UNLOCKS: dict[str, int] = {
    "horse": 50,
}

# ─── House Tier Costs ─────────────────────────

HOUSE_TIER_COSTS: dict[int, int] = {
    1: 0,
    2: 50,
    3: 100,
}


def get_unlocked_items_for_level(level: int) -> UnlockedItems:
    """Return unlocked character/accessory IDs for a given level."""
    return UnlockedItems(
        characters=[k for k, v in CHARACTER_UNLOCKS.items() if v <= level],
        accessories=[k for k, v in ACCESSORY_UNLOCKS.items() if v <= level],
    )


# ─── Stage promotion XP ───────────────────────
#
# Awarded when a tracked-repo PR merges into one of the repo's configured
# stage branches (develop / uat / main). The amount is split equally among
# everyone who contributed commits or PRs to the affected BUD, rounded to
# 2 decimal places. Dedup is per (user_id, bud_id, stage), so the same
# developer earns three credits as a BUD progresses through stages.
# If a stage's branch column on ``tracked_repositories`` is NULL, the stage
# is opted out and no XP fires for any merge — branch column existence is
# the opt-in signal.

XP_STAGE_DEVELOP = 5
XP_STAGE_UAT = 15
XP_STAGE_PROD = 25

STAGE_XP: dict[str, int] = {
    "develop": XP_STAGE_DEVELOP,
    "uat": XP_STAGE_UAT,
    "prod": XP_STAGE_PROD,
}
