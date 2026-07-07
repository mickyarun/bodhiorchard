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

"""XP/SP aggregation across a member merge.

Regression coverage for the "orphaned points" defect: merging two GitHub
identities for the same person deactivated the source but never folded its
``DeveloperXP`` row or ``reward_events`` into the target. Because the
leaderboard ranks by ``DeveloperXP`` keyed on ``user_id`` and skips inactive
members, the source dropped off (one entry now) while its XP and skill points
silently vanished instead of combining onto the surviving account.

Verified end-to-end against a real Postgres:

1. ``merge_into_target`` sums total_xp + skill_points, keeps the best streak /
   house tier / vehicle unlocks, recomputes level, and deletes the source row.
2. ``repoint_user`` re-attributes the source's reward-event history.
3. After the merge the leaderboard shows a single row carrying the combined
   XP — the exact symptom the user reported.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.developer_xp import DeveloperXP, RewardEvent, RewardType
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.repositories.developer_xp import DeveloperXPRepository, RewardEventRepository

pytestmark = pytest.mark.integration


def _unique(prefix: str) -> str:
    """Email with a per-call uuid suffix so tests sharing the DB don't collide."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


async def _seed_org(factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with factory() as db:
        org = Organization(
            name=f"XP Merge Org {uuid.uuid4()}",
            slug=f"xpmerge-{uuid.uuid4().hex[:8]}",
        )
        db.add(org)
        await db.commit()
        return org.id


async def _seed_member_with_xp(
    factory: async_sessionmaker[AsyncSession],
    org_id: uuid.UUID,
    *,
    total_xp: int,
    skill_points: float,
    streak_best: int = 0,
    house_level: int = 1,
    vehicle_unlocks: list[str] | None = None,
    reward_events: int = 0,
) -> uuid.UUID:
    """Create a member plus a DeveloperXP row and some reward events."""
    async with factory() as db:
        user = User(
            email=_unique("m"),
            name="member",
            password_hash="x",
            is_active=True,
        )
        db.add(user)
        await db.flush()
        db.add(OrgToUser(user_id=user.id, org_id=org_id))
        db.add(
            DeveloperXP(
                user_id=user.id,
                org_id=org_id,
                total_xp=total_xp,
                skill_points=skill_points,
                streak_best=streak_best,
                house_level=house_level,
                vehicle_unlocks=vehicle_unlocks or [],
            )
        )
        for i in range(reward_events):
            db.add(
                RewardEvent(
                    user_id=user.id,
                    org_id=org_id,
                    type=RewardType.XP,
                    amount=10,
                    source="pr_merged",
                    source_ref=f"pr_{user.id}_{i}",
                )
            )
        await db.commit()
        return user.id


@pytest.mark.asyncio
async def test_merge_folds_xp_sp_and_events_into_target(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Source XP/SP + reward history combine onto the target on merge."""
    org_id = await _seed_org(pg_session_factory)
    target_id = await _seed_member_with_xp(
        pg_session_factory,
        org_id,
        total_xp=120,
        skill_points=3.0,
        streak_best=4,
        house_level=1,
        vehicle_unlocks=["scooter"],
        reward_events=2,
    )
    source_id = await _seed_member_with_xp(
        pg_session_factory,
        org_id,
        total_xp=500,
        skill_points=7.5,
        streak_best=9,
        house_level=2,
        vehicle_unlocks=["scooter", "sedan"],
        reward_events=3,
    )

    async with pg_session_factory() as db:
        xp_repo = DeveloperXPRepository(db, org_id=org_id)
        moved = await xp_repo.merge_into_target(source_id, target_id)
        event_repo = RewardEventRepository(db, org_id=org_id)
        repointed = await event_repo.repoint_user(source_id, target_id)
        await db.commit()

    assert moved == {"xp": 500.0, "sp": 7.5}
    assert repointed == 3

    async with pg_session_factory() as db:
        rows = (
            (await db.execute(select(DeveloperXP).where(DeveloperXP.org_id == org_id)))
            .scalars()
            .all()
        )
        # Source row is gone; only the target survives.
        assert len(rows) == 1
        merged = rows[0]
        assert merged.user_id == target_id
        assert merged.total_xp == 620
        assert merged.skill_points == 10.5
        assert merged.streak_best == 9
        assert merged.house_level == 2
        assert merged.vehicle_unlocks == ["scooter", "sedan"]
        # 620 XP crosses the "ancient_oak" (5000) no, "tree" (1500) no — sapling.
        assert merged.level_name == "sapling"

        # Every reward event now belongs to the target.
        events = (
            (await db.execute(select(RewardEvent).where(RewardEvent.org_id == org_id)))
            .scalars()
            .all()
        )
        assert len(events) == 5
        assert {e.user_id for e in events} == {target_id}


@pytest.mark.asyncio
async def test_leaderboard_shows_single_combined_entry_after_merge(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The reported symptom: one leaderboard row carrying the combined XP."""
    org_id = await _seed_org(pg_session_factory)
    target_id = await _seed_member_with_xp(
        pg_session_factory, org_id, total_xp=100, skill_points=1.0
    )
    source_id = await _seed_member_with_xp(
        pg_session_factory, org_id, total_xp=250, skill_points=2.0
    )

    async with pg_session_factory() as db:
        xp_repo = DeveloperXPRepository(db, org_id=org_id)
        await xp_repo.merge_into_target(source_id, target_id)
        # Handler deactivates the source; mirror that so the leaderboard filter
        # (is_active) reflects production behaviour.
        source = await db.get(User, source_id)
        assert source is not None
        source.is_active = False
        await db.commit()

    async with pg_session_factory() as db:
        xp_repo = DeveloperXPRepository(db, org_id=org_id)
        board = await xp_repo.get_leaderboard()
        assert len(board) == 1
        user, xp = board[0]
        assert user.id == target_id
        assert xp is not None
        assert xp.total_xp == 350


@pytest.mark.asyncio
async def test_merge_into_target_is_idempotent(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Re-running the merge (e.g. a retried request) must not double-count."""
    org_id = await _seed_org(pg_session_factory)
    target_id = await _seed_member_with_xp(
        pg_session_factory, org_id, total_xp=100, skill_points=1.0
    )
    source_id = await _seed_member_with_xp(
        pg_session_factory, org_id, total_xp=250, skill_points=2.0
    )

    async with pg_session_factory() as db:
        xp_repo = DeveloperXPRepository(db, org_id=org_id)
        first = await xp_repo.merge_into_target(source_id, target_id)
        second = await xp_repo.merge_into_target(source_id, target_id)
        await db.commit()

    assert first == {"xp": 250.0, "sp": 2.0}
    assert second == {"xp": 0.0, "sp": 0.0}

    async with pg_session_factory() as db:
        target = await DeveloperXPRepository(db, org_id=org_id).get_by_user(target_id)
        assert target is not None
        assert target.total_xp == 350
        assert target.skill_points == 3.0
