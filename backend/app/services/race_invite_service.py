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

from app.config import settings
from app.core.encryption import decrypt_secret
from app.models.notification import Notification, NotificationType
from app.repositories.notification import NotificationRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.services.colyseus_bridge import publish_to_colyseus_room
from app.services.event_bus import publish
from app.services.slack_client import chat_post_message, conversations_open

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

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

    # Fires pre-commit, same window as the WS publish above. If the
    # commit later fails the recipient still has a working Slack DM —
    # the Colyseus race room exists independently of the DB row, so the
    # deep link still resolves.
    await _send_race_invite_slack(
        db,
        org_id=uuid.UUID(org_id),
        recipient_user_id=uuid.UUID(recipient_user_id),
        host_name=host_name,
        room_id=room_id,
        distance_m=distance_m,
    )

    return notif_id


async def _send_race_invite_slack(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    recipient_user_id: uuid.UUID,
    host_name: str,
    room_id: str,
    distance_m: int,
) -> None:
    """Best-effort Slack DM mirror of an in-app race invite.

    Fires automatically when both the recipient has a linked ``slack_id``
    and the org has a configured ``slack_bot_token``. Failure modes —
    missing identity, decryption error, Slack API timeout, ``missing_scope``
    response — all short-circuit silently so the primary in-app
    notification path is never affected. The caller does not need to
    handle a return value: this is fire-and-forget by design.
    """
    try:
        user = await UserRepository(db).get_by_id_in_org(recipient_user_id, org_id)
        if user is None or not user.slack_id:
            return

        encrypted_token = await OrganizationRepository(db).get_slack_bot_token(org_id)
        if not encrypted_token:
            return

        bot_token = decrypt_secret(encrypted_token)
        if not bot_token:
            logger.error(
                "race_invite_slack_token_decrypt_failed",
                org_id=str(org_id),
                room_id=room_id,
            )
            return

        dm_channel = await conversations_open(bot_token, user.slack_id)
        if dm_channel is None:
            # slack_client already logged the underlying reason
            # (including ``missing_scope`` if im:write hasn't been granted).
            # Tie the failure back to this specific invite so triage
            # ("why didn't Bob get a DM for room X?") doesn't have to
            # correlate by timestamp.
            logger.info(
                "race_invite_slack_skipped",
                reason="dm_open_failed",
                recipient_user_id=str(recipient_user_id),
                room_id=room_id,
            )
            return

        deep_link = f"{settings.frontend_url.rstrip('/')}/raceview/{room_id}"
        message = f"🏁 *{host_name}* invited you to a *{distance_m}m race*.\nJoin: {deep_link}"

        result = await chat_post_message(bot_token, dm_channel, message)
        if result is None:
            logger.info(
                "race_invite_slack_skipped",
                reason="post_message_failed",
                recipient_user_id=str(recipient_user_id),
                room_id=room_id,
            )
            return

        logger.info(
            "race_invite_sent_via_slack",
            recipient_user_id=str(recipient_user_id),
            room_id=room_id,
        )
    except Exception as exc:
        # Defence in depth — chat_post_message does not wrap its httpx
        # call, and decrypt_secret can raise on a corrupted key. Either
        # way, the in-app notification has already been written and the
        # WS publish has already fired; the user gets the invite.
        logger.warning(
            "race_invite_slack_send_failed",
            recipient_user_id=str(recipient_user_id),
            org_id=str(org_id),
            room_id=room_id,
            error_class=type(exc).__name__,
            exc_info=True,
        )


async def decline_race_invite(
    db: AsyncSession,
    *,
    notification_id: uuid.UUID,
    current_user: User,
) -> uuid.UUID | None:
    """Mark an invitee's race-invite as declined and notify the host.

    Idempotent on the invitee side: dismissing-then-declining is a no-op.
    The host receives a *new* notification — a fresh row rather than a
    flag toggle on the original — so the bell's existing render path,
    WS push, and unread counters all work unmodified. Returns the new
    host-side notification id, or ``None`` if the original isn't a
    race-invite owned by the caller (404 at the API layer).

    Trade-offs worth knowing:

    * The host-side notification is written unconditionally — even if
      the race has already advanced past ``lobby``. The multiplayer's
      ``RaceRoom.removeInvitee`` is phase-guarded and silently no-ops
      in that case, but the host can still receive "X declined" mid
      countdown/run. That window is short (the countdown is 3 s, the
      race itself ~15 s), and a notification that arrives during a
      live race is an honest signal anyway.
    * If ``publish_to_colyseus`` fails, the invitee's notification is
      already dismissed and the host's notification is already written
      — Alice's lobby just keeps the declined slot up until
      ``LOBBY_MAX_MS`` expires. Acceptable given the fire-and-forget
      design; do not switch this to await + roll back on failure
      without also bringing the publish inside the same transaction.

    Args:
        db: Async SQLAlchemy session.
        notification_id: id of the invitee's pending race-invite row.
        current_user: the invitee — used for scoping the lookup and for
            the display name shown on the host's bell.
    """
    repo = NotificationRepository(db, user_id=current_user.id)
    original = await repo.get_by_id(notification_id)
    if original is None or original.type != NotificationType.RACE_INVITE:
        return None
    if original.is_dismissed:
        return None

    # Originals carry host + room + distance in meta — see send_race_invite.
    meta = dict(original.meta or {})
    host_user_id = meta.get("hostUserId")
    room_id = meta.get("roomId")
    distance_m = meta.get("distanceM")
    if not isinstance(host_user_id, str) or not isinstance(room_id, str):
        # Older invite from before this schema settled — dismiss but don't
        # surface the missing meta to the user. Log so a malformed *current*
        # invite doesn't disappear without trace.
        logger.warning(
            "race_invite_decline_meta_malformed",
            notification_id=str(notification_id),
            meta_keys=sorted(meta.keys()),
        )
        original.is_dismissed = True
        await db.flush()
        return None

    # Cross-org safety: the host_user_id we're about to address came from
    # the invitee's notification meta — readable but mutable surface area
    # (whatever middleware ever touches a notification row). Verify the
    # host actually has an OrgToUser membership in this notification's
    # org before writing a bell entry under their account. If they don't,
    # silently dismiss — the host that meta points at is either gone or
    # was never legitimate, and we should not address a stranger.
    try:
        host_uuid = uuid.UUID(host_user_id)
    except ValueError:
        original.is_dismissed = True
        await db.flush()
        return None
    user_repo = UserRepository(db)
    if not await user_repo.is_member_of_org(host_uuid, original.org_id):
        logger.warning(
            "race_invite_decline_host_org_mismatch",
            host_user_id=host_user_id,
            org_id=str(original.org_id),
            invitee_user_id=str(current_user.id),
        )
        original.is_dismissed = True
        await db.flush()
        return None

    original.is_dismissed = True
    await db.flush()

    invitee_name = current_user.name or current_user.email
    distance_label = f"{distance_m} m" if isinstance(distance_m, int) else "race"
    host_title = "Race invitation declined"
    host_message = f"{invitee_name} declined your {distance_label} race invite"
    host_deep_link = f"/raceview/{room_id}"
    # Whitelist only the fields the host actually needs — spreading
    # `meta` would propagate `hostUserId=self`, which reads confusingly
    # on the host's own row and risks future code conflating the two.
    host_meta: dict[str, object] = {
        "roomId": room_id,
        "declinedBy": str(current_user.id),
        "declinedByName": invitee_name,
    }
    if isinstance(distance_m, int):
        host_meta["distanceM"] = distance_m

    host_notif_id = uuid.uuid4()
    host_notif = Notification(
        id=host_notif_id,
        org_id=original.org_id,
        user_id=host_uuid,
        type=NotificationType.RACE_INVITE,
        title=host_title,
        message=host_message,
        deep_link=host_deep_link,
        job_id=room_id,
        job_type="race_invite",
        meta=host_meta,
    )
    db.add(host_notif)
    await db.flush()

    try:
        publish(
            f"notifications:{host_user_id}",
            {
                "id": str(host_notif_id),
                "type": NotificationType.RACE_INVITE.value,
                "jobId": room_id,
                "jobType": "race_invite",
                "title": host_title,
                "message": host_message,
                "deepLink": host_deep_link,
                "isRead": False,
                "isDismissed": False,
                "createdAt": _dt.datetime.now(_dt.UTC).isoformat(),
                "meta": host_meta,
            },
        )
    except Exception:
        logger.exception(
            "race_invite_decline_ws_publish_failed",
            host_user_id=host_user_id,
            room_id=room_id,
        )

    # Tell the multiplayer to drop the declined invitee from
    # state.invitedUserIds so the host's lobby stops rendering them as
    # "Hasn't joined yet". Routed by room id, not org id — the RaceRoom
    # lifecycle is independent of which OrgRoom is currently alive (the
    # host may have left their dashboard tab the moment they hit Start).
    # Fire-and-forget — multiplayer being down means Alice's UI just
    # won't update until the next room state push, but the notification
    # side of the decline already succeeded.
    try:
        await publish_to_colyseus_room(
            room_id,
            "race_invite_declined",
            {"userId": str(current_user.id)},
        )
    except Exception:
        logger.exception(
            "race_invite_decline_colyseus_publish_failed",
            room_id=room_id,
            user_id=str(current_user.id),
        )

    return host_notif_id
