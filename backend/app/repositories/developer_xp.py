"""Repository for DeveloperXP and XPEvent queries."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.developer_xp import DeveloperXP, XPEvent
from app.models.user import User


class DeveloperXPRepository:
    """Query and update developer XP records."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id

    async def get_or_create(self, user_id: uuid.UUID) -> DeveloperXP:
        """Get the XP row for a user, creating one with defaults if absent.

        Uses SELECT ... FOR UPDATE to prevent race conditions when two
        concurrent events try to award XP to the same user. Handles the
        INSERT race (first-ever award) via IntegrityError retry.
        """
        from sqlalchemy.exc import IntegrityError

        stmt = (
            select(DeveloperXP)
            .where(DeveloperXP.user_id == user_id, DeveloperXP.org_id == self.org_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            try:
                async with self.db.begin_nested():
                    row = DeveloperXP(user_id=user_id, org_id=self.org_id)
                    self.db.add(row)
            except IntegrityError:
                # Concurrent insert won — re-fetch with lock
                result = await self.db.execute(stmt)
                row = result.scalar_one_or_none()

        return row

    async def get_by_user(self, user_id: uuid.UUID) -> DeveloperXP | None:
        """Get XP record without locking (read-only)."""
        stmt = select(DeveloperXP).where(
            DeveloperXP.user_id == user_id,
            DeveloperXP.org_id == self.org_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_leaderboard(self, limit: int = 20) -> list[tuple[User, DeveloperXP | None]]:
        """All org members ranked by XP (includes members with 0 XP)."""
        from sqlalchemy import func as sa_func

        from app.models.user import OrgToUser

        stmt = (
            select(User, DeveloperXP)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .outerjoin(
                DeveloperXP,
                (DeveloperXP.user_id == User.id) & (DeveloperXP.org_id == self.org_id),
            )
            .where(OrgToUser.org_id == self.org_id)
            .where(User.is_active.is_(True))
            .order_by(sa_func.coalesce(DeveloperXP.total_xp, 0).desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.tuples().all())


class XPEventRepository:
    """Query XP event history."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id

    async def has_source_ref(self, source_ref: str) -> bool:
        """Check if an XP event with this source_ref already exists (dedup)."""
        stmt = (
            select(XPEvent.id)
            .where(XPEvent.source_ref == source_ref, XPEvent.org_id == self.org_id)
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        xp_amount: int,
        source: str,
        source_ref: str | None = None,
        multiplier: float = 1.0,
        metadata: dict | None = None,
    ) -> XPEvent:
        """Record an XP award event."""
        event = XPEvent(
            user_id=user_id,
            org_id=self.org_id,
            xp_amount=xp_amount,
            source=source,
            source_ref=source_ref,
            multiplier=multiplier,
            metadata_=metadata,
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def list_for_user(
        self, user_id: uuid.UUID, limit: int = 50,
    ) -> list[XPEvent]:
        """Recent XP events for a user, newest first."""
        stmt = (
            select(XPEvent)
            .where(XPEvent.user_id == user_id, XPEvent.org_id == self.org_id)
            .order_by(XPEvent.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
