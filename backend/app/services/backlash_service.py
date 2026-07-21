# Copyright 2025-2026 Arun Rajkumar
# Licensed under the Apache License, Version 2.0

"""Validation and orchestration for Backlash match results and standings."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backlash import BacklashPlayerStats
from app.repositories.backlash import (
    BacklashLeaderboardRow,
    BacklashMatchInput,
    BacklashRepository,
)
from app.repositories.user import UserRepository

_ROOM_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_MATCH_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}:[1-9][0-9]{0,5}$")
_OUTCOME_REASONS = {
    "win": {"all_pieces", "no_legal_moves"},
    "draw": {"repetition", "no_progress"},
    "forfeit": {"timeout", "disconnect"},
}
_MAX_DURATION_MS = 24 * 60 * 60 * 1000
_MAX_MOVE_COUNT = 65_535


class BacklashValidationError(ValueError):
    pass


@dataclass(slots=True, frozen=True)
class BacklashResultRequest:
    match_id: str
    room_id: str
    org_id: uuid.UUID
    white_user_id: uuid.UUID
    black_user_id: uuid.UUID
    winner_user_id: uuid.UUID | None
    outcome: str
    reason: str
    move_count: int
    duration_ms: int


def stats_payload(stats: BacklashPlayerStats) -> dict[str, object]:
    return {
        "userId": str(stats.user_id),
        "wins": stats.wins,
        "losses": stats.losses,
        "draws": stats.draws,
        "matches": stats.matches,
        "currentStreak": stats.current_streak,
        "bestStreak": stats.best_streak,
    }


async def record_backlash_result(
    db: AsyncSession,
    request: BacklashResultRequest,
) -> tuple[bool, list[BacklashPlayerStats]]:
    await _validate_result(db, request)
    repo = BacklashRepository(db, org_id=request.org_id)
    claimed = await repo.try_claim_match(
        BacklashMatchInput(
            match_id=request.match_id,
            room_id=request.room_id,
            white_user_id=request.white_user_id,
            black_user_id=request.black_user_id,
            winner_user_id=request.winner_user_id,
            outcome=request.outcome,
            reason=request.reason,
            move_count=request.move_count,
            duration_ms=request.duration_ms,
        )
    )
    if not claimed:
        existing = [
            stats
            for user_id in (request.white_user_id, request.black_user_id)
            if (stats := await repo.get_stats(user_id)) is not None
        ]
        return False, existing

    today = datetime.now(UTC).date()
    if request.outcome == "draw":
        white_result = black_result = "draw"
    else:
        white_result = "win" if request.winner_user_id == request.white_user_id else "loss"
        black_result = "win" if request.winner_user_id == request.black_user_id else "loss"
    white_stats = await repo.record_player_result(
        user_id=request.white_user_id, result=white_result, today=today
    )
    black_stats = await repo.record_player_result(
        user_id=request.black_user_id, result=black_result, today=today
    )
    return True, [white_stats, black_stats]


async def get_backlash_stats(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> BacklashPlayerStats | None:
    return await BacklashRepository(db, org_id=org_id).get_stats(user_id)


async def get_backlash_leaderboard(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    limit: int,
) -> list[BacklashLeaderboardRow]:
    return await BacklashRepository(db, org_id=org_id).leaderboard(limit=max(1, min(limit, 50)))


async def _validate_result(db: AsyncSession, request: BacklashResultRequest) -> None:
    if not _ROOM_ID_RE.fullmatch(request.room_id):
        raise BacklashValidationError("invalid room_id")
    if not _MATCH_ID_RE.fullmatch(request.match_id):
        raise BacklashValidationError("invalid match_id")
    if not request.match_id.startswith(f"{request.room_id}:"):
        raise BacklashValidationError("match_id must belong to room_id")
    if request.white_user_id == request.black_user_id:
        raise BacklashValidationError("players must be distinct")
    if request.outcome not in _OUTCOME_REASONS:
        raise BacklashValidationError("invalid outcome")
    if request.reason not in _OUTCOME_REASONS[request.outcome]:
        raise BacklashValidationError("reason does not match outcome")
    participants = {request.white_user_id, request.black_user_id}
    if request.outcome == "draw" and request.winner_user_id is not None:
        raise BacklashValidationError("draw cannot have a winner")
    if request.outcome != "draw" and request.winner_user_id not in participants:
        raise BacklashValidationError("winner must be a participant")
    if not 0 <= request.move_count <= _MAX_MOVE_COUNT:
        raise BacklashValidationError("move_count out of range")
    if not 0 <= request.duration_ms <= _MAX_DURATION_MS:
        raise BacklashValidationError("duration_ms out of range")
    users = UserRepository(db)
    for user_id in participants:
        if not await users.is_member_of_org(user_id, request.org_id):
            raise BacklashValidationError("player is not a member of the organization")
