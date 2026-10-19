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

"""Tell approvers about new requests and requesters about decisions.

In-app notifications are written in the caller's transaction. Slack DMs
go out in the background on their own session, best effort. Messages
never include the leave type or reason: sick leave stays private even in
a manager's DMs.
"""

import asyncio
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.encryption import decrypt_secret
from app.database import AsyncSessionLocal
from app.models.leave_request import LeaveRequest, LeaveStatus
from app.models.notification import Notification, NotificationType
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.services.event_bus import publish
from app.services.leave.messages import compose_decision_message, compose_request_message
from app.services.notifications import NotificationCategory, category_default
from app.services.slack_client import chat_post_message, conversations_open

logger = structlog.get_logger(__name__)

# Holds fire-and-forget DM tasks so they aren't garbage-collected mid-send.
_tasks: set[asyncio.Task[None]] = set()


def _notify_in_app(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_ids: set[uuid.UUID],
    kind: NotificationType,
    title: str,
    message: str,
    link: str,
) -> None:
    for user_id in user_ids:
        note = Notification(
            id=uuid.uuid4(),
            org_id=org_id,
            user_id=user_id,
            type=kind,
            title=title,
            message=message,
            deep_link=link,
        )
        db.add(note)
        publish(
            f"notifications:{user_id}",
            {
                "id": str(note.id),
                "type": kind.value,
                "title": title,
                "message": message,
                "deepLink": link,
                "isRead": False,
                "isDismissed": False,
                "createdAt": datetime.now(UTC).isoformat(),
            },
        )


async def _dm(
    org_id: uuid.UUID, user_ids: set[uuid.UUID], category: NotificationCategory, text: str
) -> None:
    async with AsyncSessionLocal() as session:
        encrypted = await OrganizationRepository(session).get_slack_bot_token(org_id)
        token = decrypt_secret(encrypted) if encrypted else ""
        if not token:
            return
        pairs = await UserRepository(session).list_slack_recipients(
            org_id,
            category=category,
            default_enabled=category_default(category),
            user_ids=user_ids,
        )
    for _user_id, slack_id in pairs:
        try:
            channel = await conversations_open(token, slack_id)
            if channel:
                await chat_post_message(token, channel, text)
        except Exception:
            logger.warning("leave_slack_dm_failed", org_id=str(org_id), exc_info=True)


def _send_dm(
    org_id: uuid.UUID, user_ids: set[uuid.UUID], category: NotificationCategory, text: str
) -> None:
    if not user_ids:
        return
    task = asyncio.create_task(_dm(org_id, user_ids, category, text))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def notify_new_request(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    request: LeaveRequest,
    requester_name: str,
    targets: set[uuid.UUID],
    auto_approved: bool,
) -> None:
    """Tell approvers (or HR) about a request; an FYI if it was auto-approved."""
    message = compose_request_message(requester_name, request, auto_approved=auto_approved)
    link = "/leave/team" if auto_approved else "/leave/approvals"
    _notify_in_app(
        db,
        org_id=org_id,
        user_ids=targets,
        kind=NotificationType.LEAVE_REQUESTED,
        title="Work from home" if auto_approved else "Request to review",
        message=message,
        link=link,
    )
    _send_dm(
        org_id,
        targets,
        NotificationCategory.LEAVE_APPROVALS,
        f"{message} <{settings.frontend_url}{link}|Open in Bodhiorchard>",
    )


def notify_decision(
    db: AsyncSession, *, org_id: uuid.UUID, request: LeaveRequest, decider_name: str
) -> None:
    """Tell the requester their request was approved or rejected."""
    message = compose_decision_message(request, decider_name)
    _notify_in_app(
        db,
        org_id=org_id,
        user_ids={request.user_id},
        kind=NotificationType.LEAVE_DECIDED,
        title="Request approved" if request.status == LeaveStatus.APPROVED else "Request rejected",
        message=message,
        link="/leave",
    )
    _send_dm(
        org_id,
        {request.user_id},
        NotificationCategory.LEAVE_UPDATES,
        f"{message} <{settings.frontend_url}/leave|See details>",
    )
