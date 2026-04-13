"""Pydantic schemas for XP/gamification endpoints."""

from datetime import datetime

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
    skill_points: int = 0
    house_level: int = 2
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
    remaining_skill_points: int
    vehicle_unlocks: list[str]


class HouseUpgradeRequest(BaseModel):
    """Request to upgrade house tier with skill points."""

    target_tier: int


class HouseUpgradeResponse(BaseModel):
    """Response after upgrading house."""

    success: bool
    remaining_skill_points: int
    house_level: int


class XPEventRead(BaseModel):
    """Individual XP award event."""

    id: str
    xp_amount: int
    source: str
    source_ref: str | None = None
    multiplier: float
    created_at: datetime

    model_config = {"from_attributes": True}
