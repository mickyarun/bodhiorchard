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

"""Mini-game score data access — org-scoped reads + per-play upserts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.minigame import MinigameScore
from app.models.user import User


@dataclass(slots=True, frozen=True)
class PlayOutcome:
    """Result of recording one play, returned to the service layer."""

    best_score: int
    is_new_best: bool
    current_streak: int
    best_streak: int
    first_play_today: bool


@dataclass(slots=True, frozen=True)
class LeaderboardRow:
    user_id: uuid.UUID
    user_name: str
    best_score: int
    plays: int


class MinigameRepository:
    """Repository scoped by org_id — keeps cross-org queries impossible."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        self._db = db
        self._org_id = org_id

    async def record_play(
        self, *, user_id: uuid.UUID, game: str, score: int, today: date
    ) -> PlayOutcome:
        """Apply one play to the player's aggregate row.

        Updates the personal best, increments the play count, and advances
        the consecutive-day streak (reset if a day was skipped). Idempotent
        intent comes from ``today``: ``first_play_today`` reports whether
        this is the first play of the game today, which the streak logic
        uses so multiple plays in a day don't inflate the streak.
        """
        row = await self._get_or_create(user_id, game)

        first_play_today = row.last_played_date != today
        if first_play_today:
            if row.last_played_date == today - timedelta(days=1):
                row.current_streak += 1
            else:
                row.current_streak = 1
            row.best_streak = max(row.best_streak, row.current_streak)
            row.last_played_date = today

        is_new_best = score > row.best_score
        if is_new_best:
            row.best_score = score
        row.plays += 1

        await self._db.flush()
        return PlayOutcome(
            best_score=row.best_score,
            is_new_best=is_new_best,
            current_streak=row.current_streak,
            best_streak=row.best_streak,
            first_play_today=first_play_today,
        )

    async def list_for_user(self, user_id: uuid.UUID) -> list[MinigameScore]:
        stmt = (
            select(MinigameScore)
            .where(MinigameScore.org_id == self._org_id)
            .where(MinigameScore.user_id == user_id)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def leaderboard(self, *, game: str, limit: int) -> list[LeaderboardRow]:
        """Top-N personal bests for one game, org-scoped, ties broken by
        fewer plays (efficiency) then name. Drives the in-game leaderboard."""
        stmt = (
            select(
                MinigameScore.user_id,
                User.name,
                MinigameScore.best_score,
                MinigameScore.plays,
            )
            .join(User, User.id == MinigameScore.user_id)
            .where(MinigameScore.org_id == self._org_id)
            .where(MinigameScore.game == game)
            .where(MinigameScore.best_score > 0)
            .order_by(
                MinigameScore.best_score.desc(),
                MinigameScore.plays.asc(),
                User.name.asc(),
            )
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return [
            LeaderboardRow(
                user_id=r.user_id,
                user_name=r.name or "",
                best_score=r.best_score,
                plays=r.plays,
            )
            for r in result.all()
        ]

    async def _get_or_create(self, user_id: uuid.UUID, game: str) -> MinigameScore:
        stmt = (
            select(MinigameScore)
            .where(MinigameScore.org_id == self._org_id)
            .where(MinigameScore.user_id == user_id)
            .where(MinigameScore.game == game)
            .with_for_update()
        )
        existing = (await self._db.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return existing

        # A concurrent first play of the same game can race here: FOR UPDATE
        # locks nothing when no row exists, so two requests both reach the
        # INSERT and the second hits uq_minigame_scores_user_game. The
        # SAVEPOINT scopes that IntegrityError so the outer transaction stays
        # usable; we then re-select the row the winner inserted (now lockable).
        # Mirrors DeveloperXPRepository.get_or_create.
        row = MinigameScore(org_id=self._org_id, user_id=user_id, game=game)
        try:
            async with self._db.begin_nested():
                self._db.add(row)
            return row
        except IntegrityError:
            existing = (await self._db.execute(stmt)).scalar_one_or_none()
            if existing is None:
                raise
            return existing
