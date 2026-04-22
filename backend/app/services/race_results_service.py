# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Orchestration layer between the race-results REST endpoint and repo.

Enforces invariants that span the whole request (distance_m validation,
non-empty placings) before hitting the repository, so the DB layer sees
only sanitised inputs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.race_result import (
    LeaderboardRow,
    RaceResultInput,
    RaceResultRepository,
)

# Kept in sync with shared/race/RaceConstants.ts ALLOWED_DISTANCES_M and the
# CHECK constraint on `race_results.distance_m`.
_ALLOWED_DISTANCES_M = (100, 200)

# Hard cap per leaderboard query — the frontend never asks for more; the
# server-side cap means a rogue caller can't ask for a million rows.
_LEADERBOARD_MAX_LIMIT = 100


class RaceResultsValidationError(ValueError):
    """Raised when a post-results request has invalid inputs. Maps to HTTP 400."""


@dataclass(slots=True, frozen=True)
class PostRaceResultsRequest:
    room_id: str
    org_id: uuid.UUID
    host_user_id: uuid.UUID
    distance_m: int
    placings: list[RaceResultInput]


async def post_results(db: AsyncSession, req: PostRaceResultsRequest) -> int:
    """Persist the final placings for a completed race. Returns rows written.

    Idempotent: repeat calls with the same `room_id` replace the previous
    rows for each `user_id`. Commit is the caller's responsibility so the
    endpoint can couple the write with its response atomically.
    """
    if req.distance_m not in _ALLOWED_DISTANCES_M:
        raise RaceResultsValidationError(
            f"distance_m must be one of {_ALLOWED_DISTANCES_M}, got {req.distance_m}"
        )
    if not req.placings:
        raise RaceResultsValidationError("placings must be non-empty")
    for row in req.placings:
        if row.distance_m != req.distance_m:
            raise RaceResultsValidationError(
                f"per-row distance_m={row.distance_m} != request distance_m={req.distance_m}"
            )
        if row.place < 1:
            raise RaceResultsValidationError(f"place must be >= 1, got {row.place}")
        if row.finished and row.finish_time_ms is None:
            raise RaceResultsValidationError(
                "finished=True requires finish_time_ms to be set"
            )
        if not row.finished and row.finish_time_ms is not None:
            raise RaceResultsValidationError(
                "finished=False requires finish_time_ms=None"
            )

    repo = RaceResultRepository(db, org_id=req.org_id)
    return await repo.upsert_many(req.room_id, req.placings)


async def get_leaderboard(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    distance_m: int,
    limit: int,
) -> list[LeaderboardRow]:
    """Fastest finishers for an org at a distance, newest-first on ties."""
    if distance_m not in _ALLOWED_DISTANCES_M:
        raise RaceResultsValidationError(
            f"distance_m must be one of {_ALLOWED_DISTANCES_M}, got {distance_m}"
        )
    capped = max(1, min(limit, _LEADERBOARD_MAX_LIMIT))
    repo = RaceResultRepository(db, org_id=org_id)
    return await repo.leaderboard_by_distance(distance_m=distance_m, limit=capped)
