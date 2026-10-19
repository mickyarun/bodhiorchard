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

Two steps, around the caller's commit: ``stage_*`` adds the in-app rows
to the caller's transaction and returns a :class:`Notice`; the caller
commits, then calls :meth:`Notice.send` to push them over the websocket
and DM on Slack. Nobody hears about a request that rolled back, and a
pushed notification id always exists in the database.

Messages never include the leave type or reason: sick leave stays private
even in a manager's DMs.
"""

import asyncio
import uuid
from collections.abc import Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.leave_request import LeaveRequest, LeaveStatus
from app.models.notification import Notification, NotificationType
from app.services.event_bus import publish
from app.services.leave.messages import compose_decision_message, compose_request_message
from app.services.leave.slack_prompts import refresh_prompts, send_dm, send_prompts
from app.services.notifications import NotificationCategory

logger = structlog.get_logger(__name__)

# Holds fire-and-forget DM tasks so they aren't garbage-collected mid-send.
_tasks: set[asyncio.Task[None]] = set()


@dataclass
class Notice:
    """Notifications staged in a transaction, to send once it commits."""

    org_id: uuid.UUID
    user_ids: set[uuid.UUID]
    category: NotificationCategory
    slack_text: str
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    # Send these approvers Approve / Reject buttons instead of a plain DM.
    prompt_request_id: uuid.UUID | None = None
    # Afterwards, swap earlier prompts for this request to its outcome.
    refresh_request_id: uuid.UUID | None = None

    def send(self) -> None:
        """Push the in-app rows and start the Slack messages. Call after commit."""
        for topic, payload in self.events:
            publish(topic, payload)
        if self.user_ids and self.prompt_request_id:
            spawn(
                send_prompts(self.org_id, self.prompt_request_id, self.user_ids, self.slack_text)
            )
        elif self.user_ids:
            spawn(send_dm(self.org_id, self.user_ids, self.category, self.slack_text))
        if self.refresh_request_id:
            spawn(refresh_prompts(self.org_id, self.refresh_request_id))


def spawn(job: Coroutine[Any, Any, None]) -> None:
    """Run a Slack send in the background, holding a reference until it's done."""
    task = asyncio.create_task(job)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _stage(
    db: AsyncSession,
    notice: Notice,
    *,
    kind: NotificationType,
    title: str,
    message: str,
    link: str,
) -> Notice:
    for user_id in notice.user_ids:
        note = Notification(
            id=uuid.uuid4(),
            org_id=notice.org_id,
            user_id=user_id,
            type=kind,
            title=title,
            message=message,
            deep_link=link,
        )
        db.add(note)
        notice.events.append(
            (
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
        )
    return notice


def stage_new_request(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    request: LeaveRequest,
    requester_name: str,
    targets: set[uuid.UUID],
    auto_approved: bool,
) -> Notice:
    """Approvers (or HR) hear about a request; an FYI if it was auto-approved."""
    message = compose_request_message(requester_name, request, auto_approved=auto_approved)
    link = "/leave/team" if auto_approved else "/leave/approvals"
    notice = Notice(
        org_id=org_id,
        user_ids=set(targets),
        category=NotificationCategory.LEAVE_APPROVALS,
        # A request to decide gets buttons (and its own Open link); an FYI
        # for an auto-approved WFH is a plain DM.
        slack_text=message
        if not auto_approved
        else f"{message} <{settings.frontend_url}{link}|Open in Bodhiorchard>",
        prompt_request_id=None if auto_approved else request.id,
    )
    return _stage(
        db,
        notice,
        kind=NotificationType.LEAVE_REQUESTED,
        title="Work from home" if auto_approved else "Request to review",
        message=message,
        link=link,
    )


def stage_decision(
    db: AsyncSession, *, org_id: uuid.UUID, request: LeaveRequest, decider_name: str
) -> Notice:
    """The requester hears their request was approved or rejected."""
    message = compose_decision_message(request, decider_name)
    notice = Notice(
        org_id=org_id,
        user_ids={request.user_id},
        category=NotificationCategory.LEAVE_UPDATES,
        slack_text=f"{message} <{settings.frontend_url}/leave|See details>",
        refresh_request_id=request.id,
    )
    return _stage(
        db,
        notice,
        kind=NotificationType.LEAVE_DECIDED,
        title="Request approved" if request.status == LeaveStatus.APPROVED else "Request rejected",
        message=message,
        link="/leave",
    )


def after_cancel(org_id: uuid.UUID, request: LeaveRequest) -> Notice:
    """Approvers' Slack prompts show the request was cancelled."""
    return Notice(
        org_id=org_id,
        user_ids=set(),
        category=NotificationCategory.LEAVE_APPROVALS,
        slack_text="",
        refresh_request_id=request.id,
    )
