# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Persist + WS-broadcast a race invitation.

The race-invite flow is triggered by the Colyseus multiplayer bridge
calling `POST /internal/colyseus/race-invite` once per invitee. This
service handles input validation, DB write, and WS publish in a single
awaitable so the endpoint handler can commit atomically.

Kept separate from `notification_service` so the general-purpose job /
scan / lifecycle notification helpers don't grow a domain tangle and so
`notification_service.py` stays under the repo's file-size budget.
"""

from __future__ import annotations

import datetime as _dt
import re
import uuid
from typing import TYPE_CHECKING

import structlog

from app.services.event_bus import publish

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Keep in sync with shared/race/RaceConstants.ts ALLOWED_DISTANCES_M — the
# setup dialog, multiplayer bridge, and this endpoint all validate against
# the same set. Adding a distance means updating three places in one commit.
_ALLOWED_RACE_DISTANCES_M = (100, 200)

# Room IDs from Colyseus are short random slugs (letters/digits/`-`/`_`).
# The regex is deliberately strict — the value flows straight into a
# deep_link path, so anything outside the allowed alphabet could break
# the URL or hide prompt-injection-style payloads inside the message.
_RACE_ROOM_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class RaceInviteValidationError(ValueError):
    """Raised when a race-invite request has invalid inputs.

    Callers translate this into an HTTP 400 — the multiplayer bridge is
    expected to pre-validate, but we defend in depth so a buggy bridge
    can't write nonsense into the notifications table.
    """


def _validate(
    *,
    recipient_user_id: str,
    host_user_id: str,
    host_name: str,
    room_id: str,
    distance_m: int,
) -> None:
    """Validate race-invite fields before persisting. Raises on bad input."""
    if distance_m not in _ALLOWED_RACE_DISTANCES_M:
        raise RaceInviteValidationError(
            f"distance_m must be one of {_ALLOWED_RACE_DISTANCES_M}, got {distance_m}"
        )
    if not _RACE_ROOM_ID_RE.match(room_id):
        raise RaceInviteValidationError(f"room_id has invalid characters: {room_id!r}")
    if not host_name or len(host_name) > 120:
        raise RaceInviteValidationError("host_name must be non-empty and <= 120 chars")
    if not recipient_user_id or not host_user_id:
        raise RaceInviteValidationError("recipient_user_id and host_user_id are required")


async def send_race_invite_notification(
    db: AsyncSession,
    *,
    org_id: str,
    recipient_user_id: str,
    host_user_id: str,
    host_name: str,
    room_id: str,
    distance_m: int,
) -> uuid.UUID:
    """Persist a race-invite notification + publish on the recipient's WS topic.

    The row is added to the session but NOT committed here; the caller
    commits after its own response-building work so the whole request is
    atomic.

    Args:
        db: Async SQLAlchemy session.
        org_id, recipient_user_id, host_user_id: UUID strings.
        host_name: Display name shown in toast / bell dropdown.
        room_id: Colyseus race-room id; encoded into deep_link.
        distance_m: 100 or 200 — validated.

    Returns:
        The UUID of the persisted notification row.

    Raises:
        RaceInviteValidationError: on invalid inputs. No row is written.
    """
    _validate(
        recipient_user_id=recipient_user_id,
        host_user_id=host_user_id,
        host_name=host_name,
        room_id=room_id,
        distance_m=distance_m,
    )

    from app.models.notification import Notification, NotificationType

    notif_id = uuid.uuid4()
    deep_link = f"/raceview/{room_id}"
    title = "Race invitation"
    message = f"{host_name} invited you to a {distance_m} m race"
    meta = {
        "roomId": room_id,
        "hostUserId": host_user_id,
        "hostName": host_name,
        "distanceM": distance_m,
    }

    notif = Notification(
        id=notif_id,
        org_id=uuid.UUID(org_id),
        user_id=uuid.UUID(recipient_user_id),
        type=NotificationType.RACE_INVITE,
        title=title,
        message=message,
        deep_link=deep_link,
        job_id=room_id,
        job_type="race_invite",
        meta=meta,
    )
    db.add(notif)
    await db.flush()

    try:
        publish(
            f"notifications:{recipient_user_id}",
            {
                "id": str(notif_id),
                "type": NotificationType.RACE_INVITE.value,
                "jobId": room_id,
                "jobType": "race_invite",
                "title": title,
                "message": message,
                "deepLink": deep_link,
                "isRead": False,
                "isDismissed": False,
                "createdAt": _dt.datetime.now(_dt.UTC).isoformat(),
                "meta": meta,
            },
        )
    except Exception:
        # The row is already queued for commit — a WS publish failure only
        # means the recipient misses the live toast. They'll still see the
        # invite in the bell on next page load. Log and continue.
        logger.exception(
            "race_invite_ws_publish_failed",
            recipient_user_id=recipient_user_id,
            room_id=room_id,
        )

    return notif_id
