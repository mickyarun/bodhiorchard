# Copyright 2025-2026 Arun Rajkumar
# Licensed under the Apache License, Version 2.0

"""User and Colyseus-bridge endpoints for Backlash."""

from __future__ import annotations

import hmac
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.backlash_invite_service import (
    BacklashInviteValidationError,
    decline_backlash_invite,
    send_backlash_invite,
)
from app.services.backlash_service import (
    BacklashResultRequest,
    BacklashValidationError,
    get_backlash_leaderboard,
    get_backlash_stats,
    record_backlash_result,
    stats_payload,
)

router = APIRouter(tags=["backlash"])
internal_router = APIRouter(prefix="/internal/colyseus", tags=["internal"])


def _verify_bridge_secret(
    x_bridge_secret: str | None = Header(default=None, alias="X-Bridge-Secret"),
) -> None:
    configured = settings.colyseus.bridge_secret
    if not x_bridge_secret or not hmac.compare_digest(x_bridge_secret, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bridge secret",
        )


class BacklashInviteBody(BaseModel):
    org_id: uuid.UUID = Field(alias="orgId")
    recipient_user_id: uuid.UUID = Field(alias="recipientUserId")
    host_user_id: uuid.UUID = Field(alias="hostUserId")
    host_name: str = Field(alias="hostName", min_length=1, max_length=120)
    room_id: str = Field(alias="roomId", min_length=1, max_length=36)
    model_config = {"populate_by_name": True}


class BacklashInviteResponse(BaseModel):
    notification_id: uuid.UUID = Field(alias="notificationId")
    model_config = {"populate_by_name": True}


class BacklashResultsBody(BaseModel):
    match_id: str = Field(alias="matchId", min_length=3, max_length=128)
    room_id: str = Field(alias="roomId", min_length=1, max_length=64)
    org_id: uuid.UUID = Field(alias="orgId")
    white_user_id: uuid.UUID = Field(alias="whiteUserId")
    black_user_id: uuid.UUID = Field(alias="blackUserId")
    winner_user_id: uuid.UUID | None = Field(alias="winnerUserId")
    outcome: str = Field(max_length=16)
    reason: str = Field(max_length=32)
    move_count: int = Field(alias="moveCount", ge=0, le=65_535)
    duration_ms: int = Field(alias="durationMs", ge=0, le=86_400_000)
    model_config = {"populate_by_name": True}


class BacklashPlayerStatsRead(BaseModel):
    user_id: uuid.UUID = Field(alias="userId")
    wins: int
    losses: int
    draws: int
    matches: int
    current_streak: int = Field(alias="currentStreak")
    best_streak: int = Field(alias="bestStreak")
    model_config = {"populate_by_name": True}


class BacklashResultsResponse(BaseModel):
    recorded: bool
    players: list[BacklashPlayerStatsRead]


class BacklashLeaderboardEntry(BaseModel):
    user_id: uuid.UUID = Field(alias="userId")
    user_name: str = Field(alias="userName")
    wins: int
    losses: int
    draws: int
    matches: int
    win_rate: float = Field(alias="winRate")
    model_config = {"populate_by_name": True}


class BacklashLeaderboardResponse(BaseModel):
    entries: list[BacklashLeaderboardEntry]


class BacklashDeclineResponse(BaseModel):
    host_notification_id: uuid.UUID = Field(alias="hostNotificationId")
    model_config = {"populate_by_name": True}


@internal_router.post("/backlash-invite", response_model=BacklashInviteResponse)
async def create_backlash_invite(
    body: BacklashInviteBody,
    _: None = Depends(_verify_bridge_secret),
    db: AsyncSession = Depends(get_db),
) -> BacklashInviteResponse:
    users = UserRepository(db)
    for user_id in (body.host_user_id, body.recipient_user_id):
        if not await users.is_member_of_org(user_id, body.org_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not in organization",
            )
    try:
        notification_id = await send_backlash_invite(
            db,
            org_id=body.org_id,
            recipient_user_id=body.recipient_user_id,
            host_user_id=body.host_user_id,
            host_name=body.host_name,
            room_id=body.room_id,
        )
    except BacklashInviteValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    await db.commit()
    return BacklashInviteResponse(notificationId=notification_id)


@internal_router.post("/backlash-results", response_model=BacklashResultsResponse)
async def create_backlash_result(
    body: BacklashResultsBody,
    _: None = Depends(_verify_bridge_secret),
    db: AsyncSession = Depends(get_db),
) -> BacklashResultsResponse:
    request = BacklashResultRequest(
        match_id=body.match_id,
        room_id=body.room_id,
        org_id=body.org_id,
        white_user_id=body.white_user_id,
        black_user_id=body.black_user_id,
        winner_user_id=body.winner_user_id,
        outcome=body.outcome,
        reason=body.reason,
        move_count=body.move_count,
        duration_ms=body.duration_ms,
    )
    try:
        recorded, players = await record_backlash_result(db, request)
    except BacklashValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    await db.commit()
    return BacklashResultsResponse(
        recorded=recorded,
        players=[
            BacklashPlayerStatsRead.model_validate(stats_payload(player))
            for player in players
        ],
    )


@router.get("/status", response_model=BacklashPlayerStatsRead | None)
async def backlash_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BacklashPlayerStatsRead | None:
    player = await get_backlash_stats(db, org_id=current_user.org_id, user_id=current_user.id)
    return BacklashPlayerStatsRead.model_validate(stats_payload(player)) if player else None


@router.get("/leaderboard", response_model=BacklashLeaderboardResponse)
async def backlash_leaderboard(
    limit: int = Query(default=50, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BacklashLeaderboardResponse:
    rows = await get_backlash_leaderboard(db, org_id=current_user.org_id, limit=limit)
    return BacklashLeaderboardResponse(
        entries=[
            BacklashLeaderboardEntry(
                userId=row.user_id,
                userName=row.user_name,
                wins=row.wins,
                losses=row.losses,
                draws=row.draws,
                matches=row.matches,
                winRate=row.win_rate,
            )
            for row in rows
        ]
    )


@router.post("/invites/{notification_id}/decline", response_model=BacklashDeclineResponse)
async def decline_backlash_invite_endpoint(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BacklashDeclineResponse:
    host_notification_id = await decline_backlash_invite(
        db, notification_id=notification_id, current_user=current_user
    )
    if host_notification_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backlash invite not found",
        )
    await db.commit()
    return BacklashDeclineResponse(hostNotificationId=host_notification_id)
