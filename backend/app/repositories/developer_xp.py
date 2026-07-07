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

"""Repository for DeveloperXP and RewardEvent queries."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.developer_xp import DeveloperXP, RewardEvent, RewardType
from app.models.user import OrgToUser, User
from app.services.xp_rules import compute_level


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

        assert row is not None, "DeveloperXP row should exist after get_or_create"
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

    async def merge_into_target(
        self, source_user_id: uuid.UUID, target_user_id: uuid.UUID
    ) -> dict[str, float]:
        """Fold the source user's XP/SP aggregate into the target's row.

        The leaderboard ranks by ``DeveloperXP`` keyed on ``user_id`` and
        skips inactive users, so a merge that only deactivates the source
        strands its XP and skill points. This sums both currencies onto the
        target, reconciles the derived fields (streak bests, house tier and
        vehicle unlocks are kept, not lost), recomputes the target's level
        from the combined XP, then deletes the emptied source row so the
        ``(user_id, org_id)`` uniqueness holds and no points are orphaned.

        Idempotent: once the source row is gone, re-running returns zeros.

        Returns:
            ``{"xp": <moved_xp>, "sp": <moved_sp>}`` for audit logging.
        """
        source = await self.get_by_user(source_user_id)
        if source is None:
            return {"xp": 0.0, "sp": 0.0}

        target = await self.get_or_create(target_user_id)

        moved_xp = float(source.total_xp)
        moved_sp = float(source.skill_points)

        target.total_xp += source.total_xp
        target.skill_points += source.skill_points
        target.streak_best = max(target.streak_best, source.streak_best)
        target.streak_count = max(target.streak_count, source.streak_count)
        target.house_level = max(target.house_level, source.house_level)
        # Union of unlocks, target-first, de-duplicated while preserving order.
        target.vehicle_unlocks = list(
            dict.fromkeys([*target.vehicle_unlocks, *source.vehicle_unlocks])
        )
        if source.last_active_date is not None and (
            target.last_active_date is None or source.last_active_date > target.last_active_date
        ):
            target.last_active_date = source.last_active_date

        target.level, target.level_name = compute_level(target.total_xp)

        await self.db.delete(source)
        await self.db.flush()

        return {"xp": moved_xp, "sp": moved_sp}


class RewardEventRepository:
    """Query reward event history (XP and SP)."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id

    async def sum_xp_by_user_in_window(
        self, since: datetime, until: datetime
    ) -> dict[uuid.UUID, int]:
        """Sum XP earned per user with ``created_at`` in [since, until)."""
        result = await self.db.execute(
            select(RewardEvent.user_id, sa_func.sum(RewardEvent.amount).label("total"))
            .where(
                RewardEvent.org_id == self.org_id,
                RewardEvent.type == RewardType.XP,
                RewardEvent.created_at >= since,
                RewardEvent.created_at < until,
            )
            .group_by(RewardEvent.user_id)
        )
        return {row.user_id: int(row.total) for row in result.all()}

    async def has_source_ref(self, source_ref: str) -> bool:
        """Check if a reward event with this source_ref already exists (dedup)."""
        stmt = (
            select(RewardEvent.id)
            .where(RewardEvent.source_ref == source_ref, RewardEvent.org_id == self.org_id)
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        reward_type: RewardType,
        amount: float,
        source: str,
        source_ref: str | None = None,
        multiplier: float = 1.0,
        metadata: dict[str, Any] | None = None,
        bud_id: uuid.UUID | None = None,
    ) -> RewardEvent:
        """Record a reward event (XP or SP).

        ``bud_id`` is stored when the award is tied to a specific BUD
        (stage merges, BUD close, quality bonus) so per-BUD earnings
        queries don't have to parse the ``source_ref`` string.
        """
        event = RewardEvent(
            user_id=user_id,
            org_id=self.org_id,
            type=reward_type,
            amount=amount,
            source=source,
            source_ref=source_ref,
            multiplier=multiplier,
            metadata_=metadata,
            bud_id=bud_id,
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def repoint_user(self, source_user_id: uuid.UUID, target_user_id: uuid.UUID) -> int:
        """Re-attribute every reward event from the source user to the target.

        Keeps the audit trail and the windowed XP sums
        (:meth:`sum_xp_by_user_in_window`) pointing at the surviving member
        after a merge. The ``(source_ref, org_id)`` unique index cannot
        collide here: it already forbids two users in one org sharing a
        ``source_ref``, so re-keying ``user_id`` introduces no new duplicate.

        Returns:
            The number of events re-pointed.
        """
        result = await self.db.execute(
            update(RewardEvent)
            .where(
                RewardEvent.user_id == source_user_id,
                RewardEvent.org_id == self.org_id,
            )
            .values(user_id=target_user_id)
        )
        return result.rowcount or 0

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
    ) -> list[RewardEvent]:
        """Recent reward events for a user, newest first."""
        stmt = (
            select(RewardEvent)
            .where(RewardEvent.user_id == user_id, RewardEvent.org_id == self.org_id)
            .order_by(RewardEvent.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
