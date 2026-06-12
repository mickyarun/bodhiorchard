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

"""Garden mini-game endpoints.

GET  /v1/minigames/status      — per-game play state, personal best, streak.
POST /v1/minigames/score       — submit a finished play (no XP; updates
                                 best score + consecutive-day streak).
GET  /v1/minigames/leaderboard — top personal bests for one game.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.minigame import (
    LeaderboardEntry,
    MinigameLeaderboardRead,
    MinigameScoreIn,
    MinigameScoreResult,
    MinigameStatusRead,
)
from app.services.minigame_service import (
    MinigameValidationError,
    get_leaderboard,
    get_status,
    submit_score,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["minigames"])


@router.get("/status", response_model=MinigameStatusRead)
async def minigame_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MinigameStatusRead:
    data = await get_status(db, user_id=current_user.id, org_id=current_user.org_id)
    return MinigameStatusRead.model_validate(data)


@router.post("/score", response_model=MinigameScoreResult)
async def minigame_score(
    payload: MinigameScoreIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MinigameScoreResult:
    try:
        result = await submit_score(
            db,
            user_id=current_user.id,
            org_id=current_user.org_id,
            game=payload.game,
            score=payload.score,
        )
    except MinigameValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await db.commit()
    logger.info(
        "minigame_score",
        user_id=str(current_user.id),
        game=payload.game,
        score=payload.score,
        is_new_best=result["is_new_best"],
    )
    return MinigameScoreResult.model_validate(result)


@router.get("/leaderboard", response_model=MinigameLeaderboardRead)
async def minigame_leaderboard(
    game: str = Query(min_length=1, max_length=64),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MinigameLeaderboardRead:
    try:
        rows = await get_leaderboard(db, org_id=current_user.org_id, game=game, limit=limit)
    except MinigameValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return MinigameLeaderboardRead(
        game=game,
        entries=[
            LeaderboardEntry(
                user_id=r.user_id,
                user_name=r.user_name,
                best_score=r.best_score,
                plays=r.plays,
            )
            for r in rows
        ],
    )
