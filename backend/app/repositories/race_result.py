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

"""Race-result data access. Leaderboard reads + idempotent batch writes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_result import RaceResult
from app.models.user import User


@dataclass(slots=True, frozen=True)
class LeaderboardRow:
    """Flat row used by the leaderboard endpoint + frontend Pinia store."""

    user_id: uuid.UUID
    user_name: str
    distance_m: int
    finish_time_ms: int | None
    finished_at: object  # datetime — typed loose to avoid circular import


@dataclass(slots=True, frozen=True)
class RaceResultInput:
    """Single participant's row as supplied by the multiplayer bridge."""

    user_id: uuid.UUID
    host_user_id: uuid.UUID
    distance_m: int
    finish_time_ms: int | None
    place: int
    finished: bool
    distance_m_reached: float


class RaceResultRepository:
    """Repository scoped by org_id — keeps cross-org queries impossible."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        self._db = db
        self._org_id = org_id

    async def upsert_many(self, room_id: str, rows: list[RaceResultInput]) -> int:
        """Insert-or-update one batch of results. Idempotent on (room_id, user_id).

        Uses Postgres `ON CONFLICT … DO UPDATE` so retries replace the
        previous values instead of inserting duplicates. All rows share the
        same org_id and room_id; the caller has already validated distance_m.
        """
        if not rows:
            return 0

        values = [
            {
                "room_id": room_id,
                "org_id": self._org_id,
                "user_id": r.user_id,
                "host_user_id": r.host_user_id,
                "distance_m": r.distance_m,
                "finish_time_ms": r.finish_time_ms,
                "place": r.place,
                "finished": r.finished,
                "distance_m_reached": r.distance_m_reached,
            }
            for r in rows
        ]
        stmt = pg_insert(RaceResult).values(values)
        # Conflict target = the (room_id, user_id) uniqueness constraint.
        # Everything else is re-set from EXCLUDED so late-arriving corrections
        # (e.g. a bridge retry after a clock skew) take precedence.
        stmt = stmt.on_conflict_do_update(
            constraint="uq_race_results_room_user",
            set_={
                "finish_time_ms": stmt.excluded.finish_time_ms,
                "place": stmt.excluded.place,
                "finished": stmt.excluded.finished,
                "distance_m_reached": stmt.excluded.distance_m_reached,
                "distance_m": stmt.excluded.distance_m,
                "host_user_id": stmt.excluded.host_user_id,
            },
        )
        await self._db.execute(stmt)
        await self._db.flush()
        return len(rows)

    async def leaderboard_by_distance(
        self,
        *,
        distance_m: int,
        limit: int,
    ) -> list[LeaderboardRow]:
        """Fastest finishers for one distance, one row per user (their best).

        Without per-user dedup, a player who placed in three top times
        showed up three times in the top 10, pushing other players out.
        ROW_NUMBER() PARTITION BY user_id ORDER BY finish_time_ms keeps
        only the user's personal best and preserves `finished_at` of
        that specific row (which a `GROUP BY user_id, MIN(...)` would
        lose). The composite index `(org_id, distance_m, finish_time_ms)`
        still drives the inner ordering.

        DNFs (`finish_time_ms IS NULL`) are excluded — they appear only in
        per-user PR views, which aren't part of this milestone.
        """
        rn = (
            func.row_number()
            .over(
                partition_by=RaceResult.user_id,
                order_by=RaceResult.finish_time_ms.asc(),
            )
            .label("rn")
        )
        inner = (
            select(
                RaceResult.user_id.label("user_id"),
                User.name.label("user_name"),
                RaceResult.distance_m.label("distance_m"),
                RaceResult.finish_time_ms.label("finish_time_ms"),
                RaceResult.finished_at.label("finished_at"),
                rn,
            )
            .join(User, User.id == RaceResult.user_id)
            .where(RaceResult.org_id == self._org_id)
            .where(RaceResult.distance_m == distance_m)
            .where(RaceResult.finished_at.is_not(None))
            .where(RaceResult.finish_time_ms.is_not(None))
            .subquery()
        )
        stmt = (
            select(
                inner.c.user_id,
                inner.c.user_name,
                inner.c.distance_m,
                inner.c.finish_time_ms,
                inner.c.finished_at,
            )
            .where(inner.c.rn == 1)
            .order_by(inner.c.finish_time_ms.asc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return [
            LeaderboardRow(
                user_id=row.user_id,
                user_name=row.user_name or "",
                distance_m=row.distance_m,
                finish_time_ms=row.finish_time_ms,
                finished_at=row.finished_at,
            )
            for row in result.all()
        ]
