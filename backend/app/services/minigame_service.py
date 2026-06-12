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

"""Garden mini-game scoring + daily streak integration.

Mini-games are lightweight engagement loops in the garden dashboard
(fishing at the forest lake, pollen pop). Submitting a score:

  1. awards XP once per game per UTC day (``award_xp`` dedup via
     ``source_ref`` — replays return no award but still count as activity)
  2. ticks the shared daily streak (``check_and_award_streak`` — the same
     streak the rest of the platform uses, so playing a mini-game keeps a
     developer's streak alive)

No new tables: awards land in ``reward_events``; the streak lives on
``DeveloperXP``. Commit is the caller's (endpoint's) responsibility.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.developer_xp import (
    DeveloperXPRepository,
    RewardEventRepository,
)
from app.services.xp_service import award_xp, check_and_award_streak


class MinigameValidationError(ValueError):
    """Raised when a score submission fails validation."""


@dataclass(frozen=True)
class GameSpec:
    name: str
    base_xp: int
    score_cap: int


# Game registry — adding a game here is the only backend change it needs.
GAMES: dict[str, GameSpec] = {
    "fishing": GameSpec(name="Lake Fishing", base_xp=15, score_cap=35),
    "pollen_pop": GameSpec(name="Pollen Pop", base_xp=15, score_cap=35),
}

MAX_SCORE = 1000


def _source_ref(game: str, user_id: uuid.UUID, day: str) -> str:
    return f"minigame:{game}:{user_id}:{day}"


async def submit_score(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    game: str,
    score: int,
) -> dict[str, object]:
    """Validate, award daily XP (deduped), and tick the streak."""
    spec = GAMES.get(game)
    if spec is None:
        raise MinigameValidationError(f"unknown game: {game}")
    if not 0 <= score <= MAX_SCORE:
        raise MinigameValidationError(f"score out of range 0..{MAX_SCORE}: {score}")

    today = datetime.now(UTC).date().isoformat()
    amount = spec.base_xp + min(score, spec.score_cap)

    result = await award_xp(
        db,
        user_id=user_id,
        org_id=org_id,
        amount=float(amount),
        source="minigame",
        source_ref=_source_ref(game, user_id, today),
        metadata={"game": game, "score": score},
    )
    streak_count = await check_and_award_streak(db, user_id=user_id, org_id=org_id)

    return {
        "game": game,
        "xp_awarded": result.amount_awarded if result else 0,
        "first_play_today": result is not None,
        "total_xp": result.new_total if result else None,
        "level": result.new_level if result else None,
        "level_changed": result.level_changed if result else False,
        "streak_count": streak_count,
    }


async def get_status(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> dict[str, object]:
    """Today's play state per game plus the user's current streak."""
    today = datetime.now(UTC).date().isoformat()
    event_repo = RewardEventRepository(db, org_id=org_id)

    games = []
    for key, spec in GAMES.items():
        played = await event_repo.has_source_ref(_source_ref(key, user_id, today))
        games.append(
            {
                "key": key,
                "name": spec.name,
                "played_today": played,
                "max_xp": spec.base_xp + spec.score_cap,
            }
        )

    xp_repo = DeveloperXPRepository(db, org_id=org_id)
    row = await xp_repo.get_by_user(user_id)
    return {
        "games": games,
        "streak_count": row.streak_count if row else 0,
        "streak_best": row.streak_best if row else 0,
    }
