# Copyright 2025-2026 Arun Rajkumar
# Licensed under the Apache License, Version 2.0

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.backlash_service import (
    BacklashResultRequest,
    BacklashValidationError,
    record_backlash_result,
)

ORG_ID = uuid.uuid4()
WHITE_ID = uuid.uuid4()
BLACK_ID = uuid.uuid4()


def request(**overrides: object) -> BacklashResultRequest:
    values: dict[str, object] = {
        "match_id": "room_123:1",
        "room_id": "room_123",
        "org_id": ORG_ID,
        "white_user_id": WHITE_ID,
        "black_user_id": BLACK_ID,
        "winner_user_id": WHITE_ID,
        "outcome": "win",
        "reason": "all_pieces",
        "move_count": 42,
        "duration_ms": 120_000,
    }
    values.update(overrides)
    return BacklashResultRequest(**values)  # type: ignore[arg-type]


async def test_records_both_players_once() -> None:
    db = AsyncMock()
    repository = AsyncMock()
    repository.try_claim_match = AsyncMock(return_value=True)
    white_stats = SimpleNamespace(user_id=WHITE_ID, wins=1)
    black_stats = SimpleNamespace(user_id=BLACK_ID, losses=1)
    repository.record_player_result = AsyncMock(side_effect=[white_stats, black_stats])
    users = AsyncMock()
    users.is_member_of_org = AsyncMock(return_value=True)

    with (
        patch("app.services.backlash_service.BacklashRepository", return_value=repository),
        patch("app.services.backlash_service.UserRepository", return_value=users),
    ):
        recorded, players = await record_backlash_result(db, request())

    assert recorded is True
    assert players == [white_stats, black_stats]
    assert repository.record_player_result.await_count == 2
    assert repository.record_player_result.await_args_list[0].kwargs["result"] == "win"
    assert repository.record_player_result.await_args_list[1].kwargs["result"] == "loss"


async def test_duplicate_match_returns_stats_without_incrementing() -> None:
    db = AsyncMock()
    repository = AsyncMock()
    repository.try_claim_match = AsyncMock(return_value=False)
    repository.get_stats = AsyncMock(
        side_effect=[SimpleNamespace(user_id=WHITE_ID), SimpleNamespace(user_id=BLACK_ID)]
    )
    users = AsyncMock()
    users.is_member_of_org = AsyncMock(return_value=True)

    with (
        patch("app.services.backlash_service.BacklashRepository", return_value=repository),
        patch("app.services.backlash_service.UserRepository", return_value=users),
    ):
        recorded, players = await record_backlash_result(db, request())

    assert recorded is False
    assert len(players) == 2
    repository.record_player_result.assert_not_awaited()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"room_id": "../bad"}, "room_id"),
        ({"match_id": "other:1"}, "belong"),
        ({"black_user_id": WHITE_ID}, "distinct"),
        ({"outcome": "unknown"}, "outcome"),
        ({"outcome": "draw", "reason": "repetition", "winner_user_id": WHITE_ID}, "winner"),
        ({"outcome": "win", "reason": "timeout"}, "reason"),
        ({"winner_user_id": uuid.uuid4()}, "participant"),
        ({"move_count": -1}, "move_count"),
        ({"duration_ms": 86_400_001}, "duration_ms"),
    ],
)
async def test_rejects_invalid_results(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(BacklashValidationError, match=message):
        await record_backlash_result(AsyncMock(), request(**overrides))


async def test_rejects_cross_org_player() -> None:
    users = AsyncMock()
    users.is_member_of_org = AsyncMock(side_effect=[True, False])
    with (
        patch("app.services.backlash_service.UserRepository", return_value=users),
        pytest.raises(BacklashValidationError, match="not a member"),
    ):
        await record_backlash_result(AsyncMock(), request())
