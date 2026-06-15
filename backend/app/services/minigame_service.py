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

"""Garden mini-game scoring, streaks, and leaderboard.

Mini-games are engagement loops, INTENTIONALLY decoupled from the XP
economy — XP is earned only by real development work. Playing awards no
XP and never touches ``DeveloperXP``/``reward_events``. Instead each play:

  1. updates the player's personal best (the leaderboard key)
  2. advances a self-contained "play on consecutive days" streak

All persistence lives on ``minigame_scores`` (see MinigameRepository).
Commit is the caller's (endpoint's) responsibility.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.minigame import LeaderboardRow, MinigameRepository


class MinigameValidationError(ValueError):
    """Raised when a score submission fails validation."""


@dataclass(frozen=True)
class GameSpec:
    name: str
    max_score: int


# Game registry — adding a game here + a frontend component is all it takes.
GAMES: dict[str, GameSpec] = {
    "fishing": GameSpec(name="Lake Fishing", max_score=50),
    "pollen_pop": GameSpec(name="Pollen Pop", max_score=200),
    "firefly": GameSpec(name="Firefly Follow", max_score=50),
}

# Absolute ceiling regardless of per-game cap — guards against tampering.
MAX_SCORE = 1000


async def submit_score(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    game: str,
    score: int,
) -> dict[str, object]:
    """Validate then record the play; returns best/streak state (no XP)."""
    spec = GAMES.get(game)
    if spec is None:
        raise MinigameValidationError(f"unknown game: {game}")
    if not 0 <= score <= MAX_SCORE:
        raise MinigameValidationError(f"score out of range 0..{MAX_SCORE}: {score}")

    repo = MinigameRepository(db, org_id=org_id)
    today = datetime.now(UTC).date()
    outcome = await repo.record_play(user_id=user_id, game=game, score=score, today=today)

    return {
        "game": game,
        "score": score,
        "best_score": outcome.best_score,
        "is_new_best": outcome.is_new_best,
        "current_streak": outcome.current_streak,
        "best_streak": outcome.best_streak,
        "first_play_today": outcome.first_play_today,
    }


async def get_status(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> dict[str, object]:
    """Per-game play state + personal best + the player's best active streak."""
    today = datetime.now(UTC).date()
    repo = MinigameRepository(db, org_id=org_id)
    rows = {r.game: r for r in await repo.list_for_user(user_id)}

    games = []
    for key, spec in GAMES.items():
        row = rows.get(key)
        games.append(
            {
                "key": key,
                "name": spec.name,
                "max_score": spec.max_score,
                "best_score": row.best_score if row else 0,
                "played_today": bool(row and row.last_played_date == today),
            }
        )

    # The header chip shows the user's strongest live streak. A streak is
    # "live" only if its last play was today or yesterday — older rows are
    # stale and would otherwise show a frozen number.
    live_streak = 0
    for row in rows.values():
        if row.last_played_date and (today - row.last_played_date).days <= 1:
            live_streak = max(live_streak, row.current_streak)

    return {
        "games": games,
        "streak_count": live_streak,
    }


async def get_leaderboard(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    game: str,
    limit: int,
) -> list[LeaderboardRow]:
    if game not in GAMES:
        raise MinigameValidationError(f"unknown game: {game}")
    repo = MinigameRepository(db, org_id=org_id)
    return await repo.leaderboard(game=game, limit=limit)
