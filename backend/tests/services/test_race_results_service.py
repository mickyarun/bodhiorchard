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

"""Unit tests for `race_results_service` input validation.

Full DB integration (idempotent upsert, leaderboard ordering, cross-org
isolation) requires the live Postgres test fixture in `tests/conftest.py`
and runs in CI. This module covers the validation logic — which is where
the service catches malformed bridge payloads before they reach the DB.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.repositories.race_result import RaceResultInput
from app.services.race_results_service import (
    PostRaceResultsRequest,
    RaceResultsValidationError,
    get_leaderboard,
    post_results,
)


def _placing(**over: object) -> RaceResultInput:
    base = {
        "user_id": uuid.uuid4(),
        "host_user_id": uuid.uuid4(),
        "distance_m": 100,
        "finish_time_ms": 12_340,
        "place": 1,
        "finished": True,
        "distance_m_reached": 100.0,
    }
    base.update(over)
    return RaceResultInput(**base)  # type: ignore[arg-type]


def _request(**over: object) -> PostRaceResultsRequest:
    base = {
        "room_id": "race-xyz",
        "org_id": uuid.uuid4(),
        "host_user_id": uuid.uuid4(),
        "distance_m": 100,
        "placings": [_placing()],
    }
    base.update(over)
    return PostRaceResultsRequest(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_post_results_rejects_bad_distance() -> None:
    db = AsyncMock()
    with pytest.raises(RaceResultsValidationError, match="distance_m"):
        await post_results(db, _request(distance_m=150))
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_post_results_rejects_empty_placings() -> None:
    db = AsyncMock()
    with pytest.raises(RaceResultsValidationError, match="non-empty"):
        await post_results(db, _request(placings=[]))


@pytest.mark.asyncio
async def test_post_results_rejects_mismatched_per_row_distance() -> None:
    db = AsyncMock()
    bad = _request(
        distance_m=100,
        placings=[_placing(distance_m=200)],
    )
    with pytest.raises(RaceResultsValidationError, match="per-row distance_m"):
        await post_results(db, bad)


@pytest.mark.asyncio
async def test_post_results_rejects_finished_without_time() -> None:
    db = AsyncMock()
    bad = _request(placings=[_placing(finished=True, finish_time_ms=None)])
    with pytest.raises(RaceResultsValidationError, match="finish_time_ms"):
        await post_results(db, bad)


@pytest.mark.asyncio
async def test_post_results_rejects_unfinished_with_time() -> None:
    db = AsyncMock()
    bad = _request(
        placings=[_placing(finished=False, finish_time_ms=5_000, distance_m_reached=80.0)]
    )
    with pytest.raises(RaceResultsValidationError, match="finished=False"):
        await post_results(db, bad)


@pytest.mark.asyncio
async def test_get_leaderboard_rejects_invalid_distance() -> None:
    db = AsyncMock()
    with pytest.raises(RaceResultsValidationError, match="distance_m"):
        await get_leaderboard(db, org_id=uuid.uuid4(), distance_m=150, limit=10)
