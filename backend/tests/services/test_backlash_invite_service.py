# Copyright 2025-2026 Arun Rajkumar
# Licensed under the Apache License, Version 2.0

import datetime as dt
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.models.notification import NotificationType
from app.services.backlash_invite_service import (
    BacklashInviteValidationError,
    decline_backlash_invite,
    send_backlash_invite,
)

ORG_ID = uuid.uuid4()
HOST_ID = uuid.uuid4()
INVITEE_ID = uuid.uuid4()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"room_id": "../bad"}, "room_id"),
        ({"host_name": "   "}, "host_name"),
        ({"host_name": "x" * 121}, "host_name"),
        ({"room_id": "x" * 37}, "room_id"),
        ({"recipient_user_id": HOST_ID}, "cannot invite"),
    ],
)
async def test_send_rejects_invalid_invite(overrides: dict[str, object], message: str) -> None:
    values: dict[str, object] = {
        "org_id": ORG_ID,
        "recipient_user_id": INVITEE_ID,
        "host_user_id": HOST_ID,
        "host_name": "Host",
        "room_id": "room_123",
    }
    values.update(overrides)
    with pytest.raises(BacklashInviteValidationError, match=message):
        await send_backlash_invite(AsyncMock(), **values)  # type: ignore[arg-type]


async def test_decline_rejects_another_notification_type() -> None:
    original = SimpleNamespace(
        type=NotificationType.RACE_INVITE,
        is_dismissed=False,
    )
    repository = AsyncMock()
    repository.get_by_id = AsyncMock(return_value=original)
    current_user = SimpleNamespace(id=INVITEE_ID)

    with patch(
        "app.services.backlash_invite_service.NotificationRepository",
        return_value=repository,
    ):
        result = await decline_backlash_invite(
            AsyncMock(), notification_id=uuid.uuid4(), current_user=current_user
        )

    assert result is None


async def test_decline_dismisses_malformed_metadata() -> None:
    original = SimpleNamespace(
        type=NotificationType.MINIGAME_INVITE,
        is_dismissed=False,
        meta="not-an-object",
    )
    repository = AsyncMock()
    repository.get_by_id = AsyncMock(return_value=original)
    db = SimpleNamespace(flush=AsyncMock())
    current_user = SimpleNamespace(id=INVITEE_ID)

    with patch(
        "app.services.backlash_invite_service.NotificationRepository",
        return_value=repository,
    ):
        result = await decline_backlash_invite(
            db, notification_id=uuid.uuid4(), current_user=current_user
        )

    assert result is None
    assert original.is_dismissed is True
    db.flush.assert_awaited_once()


async def test_decline_expires_stale_invite_without_notifying_host() -> None:
    original = SimpleNamespace(
        type=NotificationType.MINIGAME_INVITE,
        is_dismissed=False,
        org_id=ORG_ID,
        meta={
            "game": "backlash",
            "roomId": "room_123",
            "hostUserId": str(HOST_ID),
            "expiresAt": (dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)).isoformat(),
        },
    )
    repository = AsyncMock()
    repository.get_by_id = AsyncMock(return_value=original)
    db = SimpleNamespace(flush=AsyncMock())
    current_user = SimpleNamespace(id=INVITEE_ID)

    with patch(
        "app.services.backlash_invite_service.NotificationRepository",
        return_value=repository,
    ):
        result = await decline_backlash_invite(
            db, notification_id=uuid.uuid4(), current_user=current_user
        )

    assert result is None
    assert original.is_dismissed is True
    db.flush.assert_awaited_once()


async def test_valid_decline_notifies_host_and_closes_lobby() -> None:
    original = SimpleNamespace(
        type=NotificationType.MINIGAME_INVITE,
        is_dismissed=False,
        org_id=ORG_ID,
        meta={
            "game": "backlash",
            "roomId": "room_123",
            "hostUserId": str(HOST_ID),
            "expiresAt": (dt.datetime.now(dt.UTC) + dt.timedelta(minutes=1)).isoformat(),
        },
    )
    repository = AsyncMock()
    repository.get_by_id = AsyncMock(return_value=original)
    users = AsyncMock()
    users.is_member_of_org = AsyncMock(return_value=True)
    bridge = AsyncMock()
    db = SimpleNamespace(add=Mock(), flush=AsyncMock())
    current_user = SimpleNamespace(id=INVITEE_ID, name="Invitee", email="invitee@example.com")

    with (
        patch(
            "app.services.backlash_invite_service.NotificationRepository",
            return_value=repository,
        ),
        patch("app.services.backlash_invite_service.UserRepository", return_value=users),
        patch("app.services.backlash_invite_service.publish"),
        patch("app.services.backlash_invite_service.publish_to_colyseus_room", bridge),
    ):
        result = await decline_backlash_invite(
            db, notification_id=uuid.uuid4(), current_user=current_user
        )

    assert isinstance(result, uuid.UUID)
    assert original.is_dismissed is True
    db.add.assert_called_once()
    bridge.assert_awaited_once_with(
        "room_123", "backlash_invite_declined", {"userId": str(INVITEE_ID)}
    )
