# Copyright 2025-2026 Arun Rajkumar
# Licensed under the Apache License, Version 2.0

"""Org-scoped Backlash persistence and leaderboard queries."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import Float, cast, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backlash import BacklashMatch, BacklashPlayerStats
from app.models.user import User
from app.repositories.base import rowcount


@dataclass(slots=True, frozen=True)
class BacklashMatchInput:
    match_id: str
    room_id: str
    white_user_id: uuid.UUID
    black_user_id: uuid.UUID
    winner_user_id: uuid.UUID | None
    outcome: str
    reason: str
    move_count: int
    duration_ms: int


@dataclass(slots=True, frozen=True)
class BacklashLeaderboardRow:
    user_id: uuid.UUID
    user_name: str
    wins: int
    losses: int
    draws: int
    matches: int
    win_rate: float


class BacklashRepository:
    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        self._db = db
        self._org_id = org_id

    async def try_claim_match(self, match: BacklashMatchInput) -> bool:
        stmt = (
            pg_insert(BacklashMatch)
            .values(
                id=uuid.uuid4(),
                match_id=match.match_id,
                room_id=match.room_id,
                org_id=self._org_id,
                white_user_id=match.white_user_id,
                black_user_id=match.black_user_id,
                winner_user_id=match.winner_user_id,
                outcome=match.outcome,
                reason=match.reason,
                move_count=match.move_count,
                duration_ms=match.duration_ms,
            )
            .on_conflict_do_nothing(constraint="uq_backlash_matches_match_id")
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return rowcount(result) > 0

    async def record_player_result(
        self,
        *,
        user_id: uuid.UUID,
        result: str,
        today: date,
    ) -> BacklashPlayerStats:
        stats = await self._get_or_create_stats(user_id)
        if result == "win":
            stats.wins += 1
        elif result == "loss":
            stats.losses += 1
        elif result == "draw":
            stats.draws += 1
        else:
            raise ValueError(f"unknown player result: {result}")
        stats.matches += 1
        if stats.last_played_date != today:
            stats.current_streak = (
                stats.current_streak + 1
                if stats.last_played_date == today - timedelta(days=1)
                else 1
            )
            stats.best_streak = max(stats.best_streak, stats.current_streak)
            stats.last_played_date = today
        await self._db.flush()
        return stats

    async def get_stats(self, user_id: uuid.UUID) -> BacklashPlayerStats | None:
        stmt = (
            select(BacklashPlayerStats)
            .where(BacklashPlayerStats.org_id == self._org_id)
            .where(BacklashPlayerStats.user_id == user_id)
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def leaderboard(self, *, limit: int) -> list[BacklashLeaderboardRow]:
        win_rate = cast(BacklashPlayerStats.wins, Float) / BacklashPlayerStats.matches
        stmt = (
            select(
                BacklashPlayerStats.user_id,
                User.name,
                BacklashPlayerStats.wins,
                BacklashPlayerStats.losses,
                BacklashPlayerStats.draws,
                BacklashPlayerStats.matches,
                win_rate.label("win_rate"),
            )
            .join(User, User.id == BacklashPlayerStats.user_id)
            .where(BacklashPlayerStats.org_id == self._org_id)
            .where(BacklashPlayerStats.matches > 0)
            .order_by(
                BacklashPlayerStats.wins.desc(),
                win_rate.desc(),
                BacklashPlayerStats.losses.asc(),
                User.name.asc(),
            )
            .limit(limit)
        )
        rows = (await self._db.execute(stmt)).all()
        return [
            BacklashLeaderboardRow(
                user_id=row.user_id,
                user_name=row.name or "",
                wins=row.wins,
                losses=row.losses,
                draws=row.draws,
                matches=row.matches,
                win_rate=round(float(row.win_rate or 0), 4),
            )
            for row in rows
        ]

    async def _get_or_create_stats(self, user_id: uuid.UUID) -> BacklashPlayerStats:
        stmt = (
            select(BacklashPlayerStats)
            .where(BacklashPlayerStats.org_id == self._org_id)
            .where(BacklashPlayerStats.user_id == user_id)
            .with_for_update()
        )
        existing = (await self._db.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return existing
        created = BacklashPlayerStats(org_id=self._org_id, user_id=user_id)
        try:
            async with self._db.begin_nested():
                self._db.add(created)
            return created
        except IntegrityError:
            existing = (await self._db.execute(stmt)).scalar_one_or_none()
            if existing is None:
                raise
            return existing
