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

"""Unit tests for `send_race_invite_notification`.

These are service-layer tests: they validate the pre-commit contract
(input checks, field population, WS payload shape) without needing the
full DB/WS plumbing. The integration with the REST endpoint + DB is
covered by the `internal_colyseus` API tests.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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
    with (
        patch("app.services.race_invite_service.publish") as mock_publish,
        patch(
            "app.services.race_invite_service._send_race_invite_slack",
            new=AsyncMock(),
        ),
    ):
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
    with (
        patch("app.services.race_invite_service.publish", failing),
        patch(
            "app.services.race_invite_service._send_race_invite_slack",
            new=AsyncMock(),
        ),
    ):
        notif_id = await send_race_invite_notification(db, **_valid_kwargs())
    assert isinstance(notif_id, uuid.UUID)
    assert len(db.added) == 1


# ---------------------------------------------------------------------------
# Slack-mirror path
#
# The four cases below cover the boundary contract of the Slack DM helper:
# - both sides configured → DM is sent with the expected payload
# - either side missing   → silently skip; the in-app path is unaffected
# - Slack API blows up    → exception is swallowed; the notification still
#                           lands on the session
# ---------------------------------------------------------------------------


def _patch_slack_inputs(
    *,
    slack_id: str | None,
    bot_token: str | None,
) -> tuple[Any, Any]:
    """Build the (UserRepository, OrganizationRepository) patches for one case.

    The repository fake always returns a User row — `slack_id=None` means
    "user exists but hasn't linked Slack", which is the distinct branch
    the SUT short-circuits on at ``if user is None or not user.slack_id``.
    """
    user = MagicMock()
    user.slack_id = slack_id

    user_repo = MagicMock()
    user_repo.get_by_id_in_org = AsyncMock(return_value=user)

    org_repo = MagicMock()
    org_repo.get_slack_bot_token = AsyncMock(return_value=bot_token)

    return (
        patch(
            "app.services.race_invite_service.UserRepository",
            return_value=user_repo,
        ),
        patch(
            "app.services.race_invite_service.OrganizationRepository",
            return_value=org_repo,
        ),
    )


@pytest.mark.asyncio
async def test_slack_skipped_when_user_has_no_slack_id() -> None:
    db = _FakeSession()
    user_patch, org_patch = _patch_slack_inputs(slack_id=None, bot_token="enc")
    with (
        patch("app.services.race_invite_service.publish"),
        user_patch,
        org_patch,
        patch(
            "app.services.race_invite_service.conversations_open",
            new=AsyncMock(),
        ) as mock_open,
        patch(
            "app.services.race_invite_service.chat_post_message",
            new=AsyncMock(),
        ) as mock_post,
    ):
        notif_id = await send_race_invite_notification(db, **_valid_kwargs())

    assert isinstance(notif_id, uuid.UUID)
    assert len(db.added) == 1
    mock_open.assert_not_called()
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_slack_skipped_when_org_has_no_token() -> None:
    db = _FakeSession()
    user_patch, org_patch = _patch_slack_inputs(slack_id="U123", bot_token=None)
    with (
        patch("app.services.race_invite_service.publish"),
        user_patch,
        org_patch,
        patch(
            "app.services.race_invite_service.conversations_open",
            new=AsyncMock(),
        ) as mock_open,
        patch(
            "app.services.race_invite_service.chat_post_message",
            new=AsyncMock(),
        ) as mock_post,
    ):
        notif_id = await send_race_invite_notification(db, **_valid_kwargs())

    assert isinstance(notif_id, uuid.UUID)
    assert len(db.added) == 1
    mock_open.assert_not_called()
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_slack_skipped_when_token_decrypt_fails() -> None:
    """A corrupted encryption key surfaces as ``decrypt_secret`` returning
    None. The helper must log + short-circuit before reaching Slack."""
    db = _FakeSession()
    user_patch, org_patch = _patch_slack_inputs(slack_id="U123", bot_token="enc")
    with (
        patch("app.services.race_invite_service.publish"),
        user_patch,
        org_patch,
        patch(
            "app.services.race_invite_service.decrypt_secret",
            return_value=None,
        ),
        patch(
            "app.services.race_invite_service.conversations_open",
            new=AsyncMock(),
        ) as mock_open,
        patch(
            "app.services.race_invite_service.chat_post_message",
            new=AsyncMock(),
        ) as mock_post,
    ):
        notif_id = await send_race_invite_notification(db, **_valid_kwargs())

    assert isinstance(notif_id, uuid.UUID)
    assert len(db.added) == 1
    mock_open.assert_not_called()
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_slack_dm_sent_when_both_configured() -> None:
    db = _FakeSession()
    user_patch, org_patch = _patch_slack_inputs(slack_id="U123", bot_token="enc")
    with (
        patch("app.services.race_invite_service.publish"),
        user_patch,
        org_patch,
        patch(
            "app.services.race_invite_service.decrypt_secret",
            return_value="xoxb-test",
        ),
        patch(
            "app.services.race_invite_service.conversations_open",
            new=AsyncMock(return_value="D999"),
        ) as mock_open,
        patch(
            "app.services.race_invite_service.chat_post_message",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_post,
        patch("app.services.race_invite_service.settings") as mock_settings,
    ):
        mock_settings.frontend_url = "https://app.example.com"
        await send_race_invite_notification(db, **_valid_kwargs())

    mock_open.assert_awaited_once_with("xoxb-test", "U123")
    mock_post.assert_awaited_once()
    token_arg, channel_arg, text_arg = mock_post.await_args.args
    assert token_arg == "xoxb-test"
    assert channel_arg == "D999"
    # Message includes host name, distance, and the absolute deep link.
    assert "Alice" in text_arg
    assert "100m race" in text_arg
    assert "https://app.example.com/raceview/race-abc123" in text_arg


@pytest.mark.asyncio
async def test_slack_failure_does_not_block_persistence() -> None:
    """If Slack chat.postMessage raises, the in-app notification is still
    on the session and the function returns normally. The user gets the
    in-app toast; the Slack DM just doesn't land."""
    db = _FakeSession()
    user_patch, org_patch = _patch_slack_inputs(slack_id="U123", bot_token="enc")
    with (
        patch("app.services.race_invite_service.publish"),
        user_patch,
        org_patch,
        patch(
            "app.services.race_invite_service.decrypt_secret",
            return_value="xoxb-test",
        ),
        patch(
            "app.services.race_invite_service.conversations_open",
            new=AsyncMock(return_value="D999"),
        ),
        patch(
            "app.services.race_invite_service.chat_post_message",
            new=AsyncMock(side_effect=RuntimeError("slack 503")),
        ),
    ):
        notif_id = await send_race_invite_notification(db, **_valid_kwargs())

    assert isinstance(notif_id, uuid.UUID)
    assert len(db.added) == 1
