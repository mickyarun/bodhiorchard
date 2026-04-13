"""Skill Point (SP) service — award, penalize, and query SP.

SP is a scarce, role-based currency. Unlike XP (free from activity), SP
rewards specific quality outcomes and penalises failures. Each award is
deduped via source_ref to prevent double-counting.
"""

import uuid
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import OrgToUser
from app.repositories.developer_xp import DeveloperXPRepository, XPEventRepository
from app.services.event_bus import publish

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
        event_repo = XPEventRepository(db, org_id=org_id)
        if await event_repo.has_source_ref(source_ref):
            logger.debug("sp_dedup_skip", source_ref=source_ref, user_id=str(user_id))
            return None

    xp_repo = DeveloperXPRepository(db, org_id=org_id)
    row = await xp_repo.get_or_create(user_id)

    old_sp = float(row.skill_points)
    new_sp = max(0.0, old_sp + amount)
    row.skill_points = Decimal(str(round(new_sp, 2)))

    # Record an XP event for audit trail (reuse existing event table)
    if source_ref:
        from sqlalchemy.exc import IntegrityError

        try:
            async with db.begin_nested():
                await XPEventRepository(db, org_id=org_id).create(
                    user_id=user_id,
                    xp_amount=0,  # No XP, just SP tracking
                    source=source,
                    source_ref=source_ref,
                    multiplier=1.0,
                    metadata={"sp_amount": amount, "sp_balance": new_sp},
                )
        except IntegrityError:
            # Restore balance — the ORM mutation happened before the savepoint
            row.skill_points = Decimal(str(round(old_sp, 2)))
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

    # Real-time notification
    publish(f"xp:{user_id}", {"skill_points": new_sp, "sp_source": source})

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
    stmt = select(OrgToUser.role).where(
        OrgToUser.user_id == user_id,
        OrgToUser.org_id == org_id,
    )
    result = await db.execute(stmt)
    role = result.scalar_one_or_none()
    return role.value if role else "developer"
