# Copyright 2025-2026 Arun Rajkumar
# Licensed under the Apache License, Version 2.0

"""Persistent in-app invitation lifecycle for two-player Backlash rooms."""

from __future__ import annotations

import datetime as dt
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

_ROOM_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,36}$")
_INVITE_TTL = dt.timedelta(minutes=5)


class BacklashInviteValidationError(ValueError):
    pass


def _notification_payload(notification: Notification) -> dict[str, object]:
    return {
        "id": str(notification.id),
        "type": NotificationType.MINIGAME_INVITE.value,
        "jobId": notification.job_id,
        "jobType": notification.job_type,
        "title": notification.title,
        "message": notification.message,
        "deepLink": notification.deep_link,
        "isRead": False,
        "isDismissed": False,
        "createdAt": dt.datetime.now(dt.UTC).isoformat(),
        "meta": notification.meta,
    }


async def send_backlash_invite(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    recipient_user_id: uuid.UUID,
    host_user_id: uuid.UUID,
    host_name: str,
    room_id: str,
) -> uuid.UUID:
    if not _ROOM_ID_RE.fullmatch(room_id):
        raise BacklashInviteValidationError("invalid room_id")
    clean_name = host_name.strip()
    if not clean_name or len(clean_name) > 120:
        raise BacklashInviteValidationError("host_name must be 1..120 characters")
    if recipient_user_id == host_user_id:
        raise BacklashInviteValidationError("cannot invite yourself")

    expires_at = dt.datetime.now(dt.UTC) + _INVITE_TTL
    notification = Notification(
        id=uuid.uuid4(),
        org_id=org_id,
        user_id=recipient_user_id,
        type=NotificationType.MINIGAME_INVITE,
        title="Backlash challenge",
        message=f"{clean_name} challenged you to Backlash",
        deep_link=f"/games/backlash/{room_id}",
        job_id=room_id,
        job_type="backlash_invite",
        meta={
            "game": "backlash",
            "roomId": room_id,
            "hostUserId": str(host_user_id),
            "hostName": clean_name,
            "expiresAt": expires_at.isoformat(),
        },
    )
    db.add(notification)
    await db.flush()
    try:
        publish(f"notifications:{recipient_user_id}", _notification_payload(notification))
    except Exception:
        logger.exception(
            "backlash_invite_ws_publish_failed",
            recipient_user_id=str(recipient_user_id),
            room_id=room_id,
        )
    await _send_backlash_invite_slack(
        db,
        org_id=org_id,
        recipient_user_id=recipient_user_id,
        host_name=clean_name,
        room_id=room_id,
    )
    return notification.id


async def _send_backlash_invite_slack(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    recipient_user_id: uuid.UUID,
    host_name: str,
    room_id: str,
) -> None:
    """Best-effort Slack DM mirror for a persisted Backlash challenge."""
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
                "backlash_invite_slack_token_decrypt_failed",
                org_id=str(org_id),
                room_id=room_id,
            )
            return
        dm_channel = await conversations_open(bot_token, user.slack_id)
        if dm_channel is None:
            logger.info(
                "backlash_invite_slack_skipped",
                reason="dm_open_failed",
                recipient_user_id=str(recipient_user_id),
                room_id=room_id,
            )
            return
        deep_link = f"{settings.frontend_url.rstrip('/')}/games/backlash/{room_id}"
        message = f"⚫ *{host_name}* challenged you to *Backlash*.\nPlay: {deep_link}"
        result = await chat_post_message(bot_token, dm_channel, message)
        if result is None:
            logger.info(
                "backlash_invite_slack_skipped",
                reason="post_message_failed",
                recipient_user_id=str(recipient_user_id),
                room_id=room_id,
            )
            return
        logger.info(
            "backlash_invite_sent_via_slack",
            recipient_user_id=str(recipient_user_id),
            room_id=room_id,
        )
    except Exception as exc:
        logger.warning(
            "backlash_invite_slack_send_failed",
            recipient_user_id=str(recipient_user_id),
            org_id=str(org_id),
            room_id=room_id,
            error_class=type(exc).__name__,
            exc_info=True,
        )


async def decline_backlash_invite(
    db: AsyncSession,
    *,
    notification_id: uuid.UUID,
    current_user: User,
) -> uuid.UUID | None:
    repository = NotificationRepository(db, user_id=current_user.id)
    original = await repository.get_by_id(notification_id)
    if (
        original is None
        or original.type != NotificationType.MINIGAME_INVITE
        or original.is_dismissed
    ):
        return None
    if not isinstance(original.meta, dict):
        original.is_dismissed = True
        await db.flush()
        return None
    meta = dict(original.meta)
    if meta.get("game") != "backlash":
        return None
    host_raw = meta.get("hostUserId")
    room_id = meta.get("roomId")
    expires_raw = meta.get("expiresAt")
    if not isinstance(host_raw, str) or not isinstance(room_id, str):
        original.is_dismissed = True
        await db.flush()
        return None
    try:
        host_user_id = uuid.UUID(host_raw)
        expires_at = (
            dt.datetime.fromisoformat(expires_raw) if isinstance(expires_raw, str) else None
        )
    except (ValueError, TypeError):
        original.is_dismissed = True
        await db.flush()
        return None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=dt.UTC)
    if expires_at is not None and expires_at <= dt.datetime.now(dt.UTC):
        original.is_dismissed = True
        await db.flush()
        return None
    if not await UserRepository(db).is_member_of_org(host_user_id, original.org_id):
        original.is_dismissed = True
        await db.flush()
        return None

    original.is_dismissed = True
    invitee_name = current_user.name or current_user.email
    host_notification = Notification(
        id=uuid.uuid4(),
        org_id=original.org_id,
        user_id=host_user_id,
        type=NotificationType.MINIGAME_INVITE,
        title="Backlash challenge declined",
        message=f"{invitee_name} declined your Backlash challenge",
        deep_link=f"/games/backlash/{room_id}",
        job_id=room_id,
        job_type="backlash_invite",
        meta={
            "game": "backlash",
            "roomId": room_id,
            "declinedBy": str(current_user.id),
            "declinedByName": invitee_name,
        },
    )
    db.add(host_notification)
    await db.flush()
    try:
        publish(f"notifications:{host_user_id}", _notification_payload(host_notification))
    except Exception:
        logger.exception("backlash_decline_ws_publish_failed", room_id=room_id)
    await publish_to_colyseus_room(
        room_id,
        "backlash_invite_declined",
        {"userId": str(current_user.id)},
    )
    return host_notification.id
