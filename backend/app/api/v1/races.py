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

"""Race-results REST endpoints.

Two routers, split by auth model:
  - `router` (user-auth'd): GET /v1/races/leaderboard — any org member may read.
  - `internal_router` (bridge-auth'd): POST /v1/races/results — only the
    Colyseus bridge may write. Mixing them in one router with two auth
    dependencies is confusing; splitting keeps each endpoint's trust
    boundary obvious at the route table.
"""

from __future__ import annotations

import hmac
import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.repositories.race_result import RaceResultInput
from app.services.race_results_service import (
    PostRaceResultsRequest,
    RaceResultsValidationError,
    get_leaderboard,
    post_results,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["races"])
internal_router = APIRouter(prefix="/internal/colyseus", tags=["internal"])


def _verify_bridge_secret(
    x_bridge_secret: str | None = Header(default=None, alias="X-Bridge-Secret"),
) -> None:
    """Match `internal_colyseus._verify_bridge_secret` exactly — constant-time."""
    configured = settings.colyseus.bridge_secret
    if not x_bridge_secret or not hmac.compare_digest(x_bridge_secret, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bridge secret",
        )


# ─── schemas ────────────────────────────────────────


class RacePlacingIn(BaseModel):
    user_id: uuid.UUID = Field(alias="userId")
    finish_time_ms: int | None = Field(default=None, alias="finishTimeMs")
    place: int
    finished: bool
    distance_m_reached: float = Field(alias="distanceMReached")
    distance_m: int = Field(alias="distanceM")

    model_config = {"populate_by_name": True}


class PostRaceResultsBody(BaseModel):
    room_id: str = Field(alias="roomId")
    org_id: uuid.UUID = Field(alias="orgId")
    host_user_id: uuid.UUID = Field(alias="hostUserId")
    distance_m: int = Field(alias="distanceM")
    placings: list[RacePlacingIn]

    model_config = {"populate_by_name": True}


class PostRaceResultsResponse(BaseModel):
    rows_written: int = Field(alias="rowsWritten")

    model_config = {"populate_by_name": True}


class LeaderboardRowOut(BaseModel):
    user_id: uuid.UUID = Field(alias="userId")
    user_name: str = Field(alias="userName")
    distance_m: int = Field(alias="distanceM")
    finish_time_ms: int | None = Field(alias="finishTimeMs")
    finished_at: datetime = Field(alias="finishedAt")

    model_config = {"populate_by_name": True}


class LeaderboardResponse(BaseModel):
    distance_m: int = Field(alias="distanceM")
    entries: list[LeaderboardRowOut]

    model_config = {"populate_by_name": True}


# ─── endpoints ──────────────────────────────────────


@internal_router.post("/race-results", response_model=PostRaceResultsResponse)
async def post_race_results(
    body: PostRaceResultsBody,
    _: None = Depends(_verify_bridge_secret),
    db: AsyncSession = Depends(get_db),
) -> PostRaceResultsResponse:
    """Persist the final placings for a completed race room.

    Called by the Colyseus multiplayer server when a `RaceRoom` disposes,
    via `BackendClient.postRaceResults`. Idempotent on `(room_id, user_id)`
    so the bridge's retry policy can't double-count.
    """
    req = PostRaceResultsRequest(
        room_id=body.room_id,
        org_id=body.org_id,
        host_user_id=body.host_user_id,
        distance_m=body.distance_m,
        placings=[
            RaceResultInput(
                user_id=p.user_id,
                host_user_id=body.host_user_id,
                distance_m=p.distance_m,
                finish_time_ms=p.finish_time_ms,
                place=p.place,
                finished=p.finished,
                distance_m_reached=p.distance_m_reached,
            )
            for p in body.placings
        ],
    )
    try:
        rows_written = await post_results(db, req)
    except RaceResultsValidationError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err

    await db.commit()
    logger.info(
        "race_results_persisted",
        room_id=body.room_id,
        org_id=str(body.org_id),
        distance_m=body.distance_m,
        rows=rows_written,
    )
    return PostRaceResultsResponse(rows_written=rows_written)


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_race_leaderboard(
    distance: int = Query(..., ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardResponse:
    """Org-scoped fastest-race leaderboard.

    The org scope comes from `current_user.org_id` — there's no query
    parameter for org, so users cannot snoop on other orgs even by
    guessing org UUIDs.
    """
    try:
        rows = await get_leaderboard(
            db,
            org_id=current_user.org_id,
            distance_m=distance,
            limit=limit,
        )
    except RaceResultsValidationError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err

    return LeaderboardResponse(
        distance_m=distance,
        entries=[
            LeaderboardRowOut(
                user_id=r.user_id,
                user_name=r.user_name,
                distance_m=r.distance_m,
                finish_time_ms=r.finish_time_ms,
                finished_at=r.finished_at,
            )
            for r in rows
        ],
    )
