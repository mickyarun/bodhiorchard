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

"""End-to-end coverage for the race-results write path + leaderboard read.

Reproducer for the production complaint: "only the winner appears on the
leaderboard, 2nd-4th finishers go missing." The existing service tests
(``tests/services/test_race_results_service.py``) mock ``db.execute``,
which is why a real failure in the upsert SQL or the leaderboard query
can hide. This module runs the same code against a real Postgres so the
batch insert and the leaderboard ``SELECT`` are both exercised.

Three properties verified end-to-end:

1. A 4-finisher payload writes 4 rows — one per user_id — and all four
   come back from ``get_leaderboard`` in ascending finish-time order.
2. DNFs (``finished=False`` + ``finish_time_ms=None``) are persisted but
   excluded from the leaderboard, since the leaderboard view shows
   completed times only.
3. A bridge retry with the same ``room_id`` updates rows in place rather
   than appending duplicates — the ``(room_id, user_id)`` unique
   constraint is doing its job.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.organization import Organization
from app.models.race_result import RaceResult
from app.models.user import OrgToUser, User
from app.repositories.race_result import RaceResultInput
from app.services.race_results_service import (
    PostRaceResultsRequest,
    get_leaderboard,
    post_results,
)

pytestmark = pytest.mark.integration


async def _seed_org_with_racers(
    factory: async_sessionmaker[AsyncSession],
    *,
    racer_count: int,
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """Create one org plus ``racer_count`` distinct users in it.

    Returns ``(org_id, [user_id, ...])`` with the user list ordered
    deterministically by the loop index so tests can refer to "the
    first racer" / "the second racer" unambiguously.
    """
    async with factory() as db:
        org = Organization(
            name=f"Race Test Org {uuid.uuid4()}",
            slug=f"race-{uuid.uuid4().hex[:8]}",
        )
        db.add(org)
        await db.flush()

        user_ids: list[uuid.UUID] = []
        for idx in range(racer_count):
            user = User(
                email=f"racer-{idx}-{uuid.uuid4().hex[:8]}@example.com",
                name=f"Racer {idx}",
                password_hash="x",
            )
            db.add(user)
            await db.flush()
            db.add(OrgToUser(user_id=user.id, org_id=org.id))
            user_ids.append(user.id)
        await db.commit()
        return org.id, user_ids


def _placing(
    *,
    user_id: uuid.UUID,
    host_user_id: uuid.UUID,
    place: int,
    finish_time_ms: int | None,
    finished: bool,
    distance_m: int = 100,
) -> RaceResultInput:
    """Build one ``RaceResultInput`` row, defaulting common fields."""
    return RaceResultInput(
        user_id=user_id,
        host_user_id=host_user_id,
        distance_m=distance_m,
        finish_time_ms=finish_time_ms,
        place=place,
        finished=finished,
        distance_m_reached=float(distance_m) if finished else 0.0,
    )


@pytest.mark.asyncio
async def test_four_finishers_all_appear_on_leaderboard(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Direct reproducer for the production complaint.

    Post a single race result payload with four finishers ranked 1-4 and
    confirm all four come back from ``get_leaderboard`` ordered by time.
    A failure here means the write path or the leaderboard query is
    dropping non-winners — the bug the user reported.
    """
    org_id, user_ids = await _seed_org_with_racers(pg_session_factory, racer_count=4)
    host_user_id = user_ids[0]
    room_id = f"race-{uuid.uuid4().hex[:8]}"

    placings = [
        _placing(
            user_id=user_ids[idx],
            host_user_id=host_user_id,
            place=idx + 1,
            finish_time_ms=14_500 + idx * 80,  # 14.50 / 14.58 / 14.66 / 14.74
            finished=True,
        )
        for idx in range(4)
    ]

    async with pg_session_factory() as db:
        rows_written = await post_results(
            db,
            PostRaceResultsRequest(
                room_id=room_id,
                org_id=org_id,
                host_user_id=host_user_id,
                distance_m=100,
                placings=placings,
            ),
        )
        await db.commit()
        assert rows_written == 4

    async with pg_session_factory() as db:
        # Sanity check at the storage layer: four rows actually landed.
        stored = (
            (await db.execute(select(RaceResult).where(RaceResult.room_id == room_id)))
            .scalars()
            .all()
        )
        assert len(stored) == 4
        assert {r.user_id for r in stored} == set(user_ids)

    async with pg_session_factory() as db:
        leaderboard = await get_leaderboard(
            db, org_id=org_id, distance_m=100, limit=50
        )

    leaderboard_user_ids = [row.user_id for row in leaderboard]
    assert leaderboard_user_ids == user_ids, (
        "Expected all four finishers on the leaderboard in finish order, got "
        f"{leaderboard_user_ids}"
    )
    assert [row.finish_time_ms for row in leaderboard] == [14_500, 14_580, 14_660, 14_740]


@pytest.mark.asyncio
async def test_dnfs_persist_but_are_excluded_from_leaderboard(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Mixed finishers + DNFs in one payload.

    Two finishers, two DNFs. The leaderboard returns the two finishers
    only; the DNFs survive in the underlying ``race_results`` table so a
    future "personal records" view can rank them by distance reached.
    """
    org_id, user_ids = await _seed_org_with_racers(pg_session_factory, racer_count=4)
    host_user_id = user_ids[0]
    room_id = f"race-{uuid.uuid4().hex[:8]}"

    placings = [
        _placing(
            user_id=user_ids[0],
            host_user_id=host_user_id,
            place=1,
            finish_time_ms=14_500,
            finished=True,
        ),
        _placing(
            user_id=user_ids[1],
            host_user_id=host_user_id,
            place=2,
            finish_time_ms=14_900,
            finished=True,
        ),
        # DNF: did not cross the line, ranked by distance_m_reached.
        RaceResultInput(
            user_id=user_ids[2],
            host_user_id=host_user_id,
            distance_m=100,
            finish_time_ms=None,
            place=3,
            finished=False,
            distance_m_reached=72.5,
        ),
        RaceResultInput(
            user_id=user_ids[3],
            host_user_id=host_user_id,
            distance_m=100,
            finish_time_ms=None,
            place=4,
            finished=False,
            distance_m_reached=55.0,
        ),
    ]

    async with pg_session_factory() as db:
        await post_results(
            db,
            PostRaceResultsRequest(
                room_id=room_id,
                org_id=org_id,
                host_user_id=host_user_id,
                distance_m=100,
                placings=placings,
            ),
        )
        await db.commit()

    async with pg_session_factory() as db:
        stored = (
            (await db.execute(select(RaceResult).where(RaceResult.room_id == room_id)))
            .scalars()
            .all()
        )
        assert len(stored) == 4, "All 4 racers (finishers + DNFs) must be persisted"

    async with pg_session_factory() as db:
        leaderboard = await get_leaderboard(
            db, org_id=org_id, distance_m=100, limit=50
        )

    finisher_ids = [user_ids[0], user_ids[1]]
    assert [row.user_id for row in leaderboard] == finisher_ids


@pytest.mark.asyncio
async def test_idempotent_replay_updates_in_place(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A bridge retry on the same room must not duplicate rows.

    Simulates the multiplayer bridge resending a payload after a transient
    backend 5xx: same ``room_id``, same user ids, slightly different
    times (e.g. clock skew correction). Post-fix the table holds one row
    per user with the *latest* values; a regression would either
    duplicate rows (no unique constraint hit) or refuse the update
    (conflict policy too strict).
    """
    org_id, user_ids = await _seed_org_with_racers(pg_session_factory, racer_count=3)
    host_user_id = user_ids[0]
    room_id = f"race-{uuid.uuid4().hex[:8]}"

    def make_payload(times_ms: list[int]) -> PostRaceResultsRequest:
        return PostRaceResultsRequest(
            room_id=room_id,
            org_id=org_id,
            host_user_id=host_user_id,
            distance_m=100,
            placings=[
                _placing(
                    user_id=user_ids[idx],
                    host_user_id=host_user_id,
                    place=idx + 1,
                    finish_time_ms=times_ms[idx],
                    finished=True,
                )
                for idx in range(3)
            ],
        )

    async with pg_session_factory() as db:
        await post_results(db, make_payload([14_500, 14_600, 14_700]))
        await db.commit()

    # Bridge retry — same room, corrected times.
    async with pg_session_factory() as db:
        await post_results(db, make_payload([14_510, 14_610, 14_710]))
        await db.commit()

    async with pg_session_factory() as db:
        stored = (
            (await db.execute(select(RaceResult).where(RaceResult.room_id == room_id)))
            .scalars()
            .all()
        )
        assert len(stored) == 3, "Retry must not duplicate rows"
        by_user = {row.user_id: row.finish_time_ms for row in stored}
        assert by_user == {
            user_ids[0]: 14_510,
            user_ids[1]: 14_610,
            user_ids[2]: 14_710,
        }


@pytest.mark.asyncio
async def test_leaderboard_keeps_every_race_entry_not_just_personal_best(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Same player across multiple races appears once per race.

    The leaderboard is a log of the fastest runs, not a highscore table.
    A player who finished in the top times twice legitimately occupies
    two slots — they earned each one. An earlier well-meant dedup
    (`ROW_NUMBER() PARTITION BY user_id`) collapsed those into "personal
    best only" and silently dropped previously-visible entries when a
    user ran another race. This test pins the no-dedup contract.

    Two users, three races. Six finishes total. The leaderboard returns
    all six, ordered by finish time ascending.
    """
    org_id, user_ids = await _seed_org_with_racers(pg_session_factory, racer_count=2)
    host_user_id = user_ids[0]

    races = [
        # room_id, [(user_idx, time_ms, place), ...]
        ("race-aaa", [(0, 15_400, 1), (1, 16_290, 2)]),
        ("race-bbb", [(0, 32_120, 2), (1, 15_360, 1)]),
        ("race-ccc", [(0, 14_900, 1), (1, 17_200, 2)]),
    ]
    for room_id, racers in races:
        placings = [
            _placing(
                user_id=user_ids[idx],
                host_user_id=host_user_id,
                place=place,
                finish_time_ms=time_ms,
                finished=True,
            )
            for idx, time_ms, place in racers
        ]
        async with pg_session_factory() as db:
            await post_results(
                db,
                PostRaceResultsRequest(
                    room_id=room_id,
                    org_id=org_id,
                    host_user_id=host_user_id,
                    distance_m=100,
                    placings=placings,
                ),
            )
            await db.commit()

    async with pg_session_factory() as db:
        leaderboard = await get_leaderboard(
            db, org_id=org_id, distance_m=100, limit=10
        )

    times = [row.finish_time_ms for row in leaderboard]
    assert times == [14_900, 15_360, 15_400, 16_290, 17_200, 32_120], (
        f"Every race entry must appear, ordered by finish time. Got {times}"
    )

    # User 0 appears three times (once per race they ran), as does user 1.
    appearances = {uid: sum(1 for r in leaderboard if r.user_id == uid) for uid in user_ids}
    assert appearances == {user_ids[0]: 3, user_ids[1]: 3}
