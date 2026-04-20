# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Unit tests for `send_race_invite_notification`.

These are service-layer tests: they validate the pre-commit contract
(input checks, field population, WS payload shape) without needing the
full DB/WS plumbing. The integration with the REST endpoint + DB is
covered by the `internal_colyseus` API tests.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.models.notification import Notification, NotificationType
from app.services.race_invite_service import (
    RaceInviteValidationError,
    send_race_invite_notification,
)


class _FakeSession:
    """Minimal AsyncSession stand-in. Captures `add` calls and awaits `flush`."""

    def __init__(self) -> None:
        self.added: list[Notification] = []

    def add(self, obj: Notification) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass


def _valid_kwargs() -> dict[str, Any]:
    return {
        "org_id": str(uuid.uuid4()),
        "recipient_user_id": str(uuid.uuid4()),
        "host_user_id": str(uuid.uuid4()),
        "host_name": "Alice",
        "room_id": "race-abc123",
        "distance_m": 100,
    }


@pytest.mark.asyncio
async def test_persists_race_invite_with_full_metadata() -> None:
    kwargs = _valid_kwargs()
    db = _FakeSession()
    with patch("app.services.race_invite_service.publish") as mock_publish:
        notif_id = await send_race_invite_notification(db, **kwargs)

    assert isinstance(notif_id, uuid.UUID)
    assert len(db.added) == 1
    notif = db.added[0]
    assert notif.type == NotificationType.RACE_INVITE
    assert notif.deep_link == "/raceview/race-abc123"
    assert notif.job_id == "race-abc123"
    assert notif.job_type == "race_invite"
    assert notif.title == "Race invitation"
    assert notif.message == "Alice invited you to a 100 m race"
    assert notif.meta == {
        "roomId": "race-abc123",
        "hostUserId": kwargs["host_user_id"],
        "hostName": "Alice",
        "distanceM": 100,
    }

    # WS broadcast fired on the recipient's topic.
    mock_publish.assert_called_once()
    topic, payload = mock_publish.call_args.args
    assert topic == f"notifications:{kwargs['recipient_user_id']}"
    assert payload["type"] == "race_invite"
    assert payload["deepLink"] == "/raceview/race-abc123"
    assert payload["meta"]["distanceM"] == 100


@pytest.mark.asyncio
async def test_rejects_invalid_distance() -> None:
    db = _FakeSession()
    bad = {**_valid_kwargs(), "distance_m": 150}
    with pytest.raises(RaceInviteValidationError, match="distance_m"):
        await send_race_invite_notification(db, **bad)
    assert db.added == []


@pytest.mark.asyncio
async def test_rejects_bad_room_id_characters() -> None:
    db = _FakeSession()
    bad = {**_valid_kwargs(), "room_id": "../etc/passwd"}
    with pytest.raises(RaceInviteValidationError, match="room_id"):
        await send_race_invite_notification(db, **bad)
    assert db.added == []


@pytest.mark.asyncio
async def test_rejects_empty_host_name() -> None:
    db = _FakeSession()
    bad = {**_valid_kwargs(), "host_name": ""}
    with pytest.raises(RaceInviteValidationError, match="host_name"):
        await send_race_invite_notification(db, **bad)


@pytest.mark.asyncio
async def test_ws_publish_failure_does_not_block_persistence() -> None:
    """If WS publish blows up we still return the notif id — the row is on
    the session, and the caller's commit will still happen. The recipient
    just misses the live toast; the bell still shows the invite."""
    db = _FakeSession()
    failing = AsyncMock(side_effect=RuntimeError("redis down"))
    with patch("app.services.race_invite_service.publish", failing):
        notif_id = await send_race_invite_notification(db, **_valid_kwargs())
    assert isinstance(notif_id, uuid.UUID)
    assert len(db.added) == 1
