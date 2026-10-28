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

"""A settable clock for one module's ``datetime``, and helpers to seed and read a streak."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, tzinfo

from sqlalchemy import select

from app.models.developer_xp import DeveloperXP, RewardEvent
from app.services.xp_service import check_and_award_streak
from tests.fakes.seed import Factory


class FrozenClock:
    """Stands in for a module's ``datetime``; ``instant`` is an aware UTC time."""

    instant = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> datetime:
        """The frozen instant, in ``tz`` like the real ``datetime.now``."""
        return cls.instant.astimezone(tz) if tz is not None else cls.instant

    @classmethod
    def set_local(cls, local: datetime) -> None:
        """Move the clock to an aware local wall time (any zone)."""
        cls.instant = local.astimezone(UTC)


async def seed_streak(
    factory: Factory,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    streak: int,
    best: int,
    last_active: date,
) -> None:
    """An XP row as if the member had been active ``streak`` days up to ``last_active``."""
    async with factory() as db:
        db.add(
            DeveloperXP(
                org_id=org_id,
                user_id=user_id,
                streak_count=streak,
                streak_best=best,
                last_active_date=last_active,
            )
        )
        await db.commit()


async def tick(factory: Factory, org_id: uuid.UUID, user_id: uuid.UUID) -> int:
    """One dev-activity event's streak check, committed; returns the streak."""
    async with factory() as db:
        streak = await check_and_award_streak(db, user_id=user_id, org_id=org_id)
        await db.commit()
        return streak


async def streak_row(factory: Factory, org_id: uuid.UUID, user_id: uuid.UUID) -> DeveloperXP:
    """The member's XP row (must exist)."""
    async with factory() as db:
        row = await db.scalar(
            select(DeveloperXP).where(DeveloperXP.org_id == org_id, DeveloperXP.user_id == user_id)
        )
        assert row is not None
        return row


async def rewards(
    factory: Factory, org_id: uuid.UUID, user_id: uuid.UUID
) -> list[tuple[str, str, float, float]]:
    """``(type, source_ref, amount, multiplier)`` of the member's events, oldest first."""
    async with factory() as db:
        rows = await db.scalars(
            select(RewardEvent)
            .where(RewardEvent.org_id == org_id, RewardEvent.user_id == user_id)
            .order_by(RewardEvent.created_at)
        )
        return [
            (r.type.value, r.source_ref or "", float(r.amount), float(r.multiplier)) for r in rows
        ]
