"""XP/gamification API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.repositories.developer_xp import DeveloperXPRepository, XPEventRepository
from app.schemas.xp import (
    HouseUpgradeRequest,
    HouseUpgradeResponse,
    LeaderboardEntry,
    VehicleUnlockRequest,
    VehicleUnlockResponse,
    XPEventRead,
    XPProfileRead,
)
from app.services.xp_rules import HOUSE_TIER_COSTS, VEHICLE_UNLOCKS
from app.services.xp_service import get_unlocked_items, xp_for_next_level

router = APIRouter(prefix="/xp", tags=["xp"])


@router.get("/me", response_model=XPProfileRead)
async def get_my_xp(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> XPProfileRead:
    """Return the current user's XP profile, level, streak, and unlocks."""
    xp_repo = DeveloperXPRepository(db, org_id=current_user.org_id)
    row = await xp_repo.get_by_user(current_user.id)

    total_xp = row.total_xp if row else 0
    level = row.level if row else 1
    level_name = row.level_name if row else "seedling"
    streak_count = row.streak_count if row else 0
    streak_best = row.streak_best if row else 0

    xp_remaining, next_threshold = xp_for_next_level(total_xp)
    unlocks = await get_unlocked_items(
        db, user_id=current_user.id, org_id=current_user.org_id,
    )

    return XPProfileRead(
        total_xp=total_xp,
        level=level,
        level_name=level_name,
        xp_to_next_level=xp_remaining,
        next_level_threshold=next_threshold,
        streak_count=streak_count,
        streak_best=streak_best,
        unlocked_characters=unlocks.characters,
        unlocked_accessories=unlocks.accessories,
        skill_points=row.skill_points if row else 0,
        house_level=row.house_level if row else 1,
        vehicle_unlocks=list(row.vehicle_unlocks) if row and row.vehicle_unlocks else [],
    )


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def get_leaderboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LeaderboardEntry]:
    """Return top developers by XP in the org."""
    xp_repo = DeveloperXPRepository(db, org_id=current_user.org_id)
    entries = await xp_repo.get_leaderboard(limit=20)

    return [
        LeaderboardEntry(
            user_id=str(user.id),
            name=user.name,
            avatar_url=user.avatar_url,
            total_xp=xp.total_xp if xp else 0,
            level=xp.level if xp else 1,
            level_name=xp.level_name if xp else "seedling",
            streak_count=xp.streak_count if xp else 0,
        )
        for user, xp in entries
    ]


@router.get("/history", response_model=list[XPEventRead])
async def get_xp_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[XPEventRead]:
    """Return recent XP events for the current user."""
    event_repo = XPEventRepository(db, org_id=current_user.org_id)
    events = await event_repo.list_for_user(current_user.id, limit=50)

    return [
        XPEventRead(
            id=str(e.id),
            xp_amount=e.xp_amount,
            source=e.source,
            source_ref=e.source_ref,
            multiplier=float(e.multiplier),
            created_at=e.created_at,
        )
        for e in events
    ]


@router.post("/unlock-vehicle", response_model=VehicleUnlockResponse)
async def unlock_vehicle(
    body: VehicleUnlockRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VehicleUnlockResponse:
    """Spend skill points to unlock a vehicle."""
    cost = VEHICLE_UNLOCKS.get(body.vehicle_id)
    if cost is None:
        raise HTTPException(400, f"Unknown vehicle '{body.vehicle_id}'")

    xp_repo = DeveloperXPRepository(db, org_id=current_user.org_id)
    row = await xp_repo.get_or_create(current_user.id)

    current_unlocks = list(row.vehicle_unlocks) if row.vehicle_unlocks else []
    if body.vehicle_id in current_unlocks:
        raise HTTPException(409, f"Vehicle '{body.vehicle_id}' already unlocked")
    if row.skill_points < cost:
        raise HTTPException(400, f"Insufficient skill points ({row.skill_points}/{cost})")

    row.skill_points -= cost
    row.vehicle_unlocks = [*current_unlocks, body.vehicle_id]
    await db.commit()

    return VehicleUnlockResponse(
        success=True,
        remaining_skill_points=row.skill_points,
        vehicle_unlocks=list(row.vehicle_unlocks),
    )


@router.post("/upgrade-house", response_model=HouseUpgradeResponse)
async def upgrade_house(
    body: HouseUpgradeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HouseUpgradeResponse:
    """Spend skill points to upgrade house tier."""
    cost = HOUSE_TIER_COSTS.get(body.target_tier)
    if cost is None:
        raise HTTPException(400, f"Unknown house tier {body.target_tier}")

    xp_repo = DeveloperXPRepository(db, org_id=current_user.org_id)
    row = await xp_repo.get_or_create(current_user.id)

    if body.target_tier != row.house_level + 1:
        raise HTTPException(400, "Can only upgrade to the next tier")
    if row.skill_points < cost:
        raise HTTPException(400, f"Insufficient skill points ({row.skill_points}/{cost})")

    row.skill_points -= cost
    row.house_level = body.target_tier
    await db.commit()

    return HouseUpgradeResponse(
        success=True,
        remaining_skill_points=row.skill_points,
        house_level=row.house_level,
    )


@router.post("/claim-greeting-bonus")
async def claim_greeting_bonus(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Award 0.25 SP for first greeting emote near each unique user.

    One award per (greeter, target) pair — greet 4 different people = 1 SP.
    The source_ref unique index prevents duplicate awards per pair.
    """
    from app.models.developer_xp import XPEvent

    target_user_id = body.get("target_user_id")
    if not target_user_id:
        raise HTTPException(400, "target_user_id required")

    xp_repo = DeveloperXPRepository(db, org_id=current_user.org_id)
    row = await xp_repo.get_or_create(current_user.id)

    # Unique per (greeter, target) pair — greet same person twice = no-op
    source_ref = f"greeting_{current_user.id}_{target_user_id}"
    existing = await db.execute(
        select(XPEvent.id).where(XPEvent.source_ref == source_ref)
    )
    if existing.scalar_one_or_none() is not None:
        return {"awarded": False, "reason": "already_greeted"}

    row.skill_points += 0.25
    db.add(XPEvent(
        user_id=current_user.id,
        org_id=current_user.org_id,
        xp_amount=0,
        source="greeting_bonus",
        source_ref=source_ref,
    ))
    await db.commit()

    return {"awarded": True, "skill_points": row.skill_points, "sp_earned": 0.25}
