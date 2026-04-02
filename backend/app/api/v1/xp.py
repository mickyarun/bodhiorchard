"""XP/gamification API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.repositories.developer_xp import DeveloperXPRepository, XPEventRepository
from app.schemas.xp import LeaderboardEntry, XPEventRead, XPProfileRead
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
            user_id=str(xp.user_id),
            name=user.name,
            avatar_url=user.avatar_url,
            total_xp=xp.total_xp,
            level=xp.level,
            level_name=xp.level_name,
            streak_count=xp.streak_count,
        )
        for xp, user in entries
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
