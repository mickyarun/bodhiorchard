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

GET  /v1/minigames/status — today's play state per game + daily streak.
POST /v1/minigames/score  — submit a finished play; awards XP once per
game per UTC day and ticks the platform-wide daily streak.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.minigame import (
    MinigameScoreIn,
    MinigameScoreResult,
    MinigameStatusRead,
)
from app.services.minigame_service import (
    MinigameValidationError,
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
        xp_awarded=result["xp_awarded"],
    )
    return MinigameScoreResult.model_validate(result)
