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

"""Pydantic schemas for XP/gamification endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class XPProfileRead(BaseModel):
    """Current user's XP profile."""

    total_xp: int
    level: int
    level_name: str
    xp_to_next_level: int
    next_level_threshold: int
    streak_count: int
    streak_best: int
    unlocked_characters: list[str]
    unlocked_accessories: list[str]
    skill_points: float = 0.0
    house_level: int = 1
    vehicle_unlocks: list[str] = []

    model_config = {"from_attributes": True}


class LeaderboardEntry(BaseModel):
    """Single entry in the org XP leaderboard."""

    user_id: str
    name: str
    avatar_url: str | None = None
    total_xp: int
    level: int
    level_name: str
    streak_count: int

    model_config = {"from_attributes": True}


class VehicleUnlockRequest(BaseModel):
    """Request to unlock a vehicle with skill points."""

    vehicle_id: str


class VehicleUnlockResponse(BaseModel):
    """Response after unlocking a vehicle."""

    success: bool
    remaining_skill_points: float
    vehicle_unlocks: list[str]


class HouseUpgradeRequest(BaseModel):
    """Request to upgrade house tier with skill points."""

    target_tier: int


class HouseUpgradeResponse(BaseModel):
    """Response after upgrading house."""

    success: bool
    remaining_skill_points: float
    house_level: int


class RewardEventRead(BaseModel):
    """Individual reward award event (XP or SP)."""

    id: str
    type: Literal["xp", "sp"]
    amount: float
    source: str
    source_ref: str | None = None
    multiplier: float
    created_at: datetime

    model_config = {"from_attributes": True}
