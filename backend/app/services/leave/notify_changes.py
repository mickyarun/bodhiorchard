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

"""Tell the requester their approved leave was changed or its approval withdrawn.

Staged in the caller's transaction like every leave notice (see
:mod:`app.services.leave.notify`): the in-app row and a Slack DM, the
approvers' Slack prompts updated, and their calendar and Slack status
brought in line once it commits.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.leave_request import LeaveRequest, LeaveStatus
from app.models.notification import NotificationType
from app.services.leave.messages import compose_change_message
from app.services.leave.notify import Notice, stage_rows
from app.services.leave.slack_blocks import escape
from app.services.notifications import NotificationCategory


def stage_change(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    request: LeaveRequest,
    actor_name: str,
    withdrawn: bool,
) -> Notice:
    """The requester hears what changed, who changed it and the note."""
    message = compose_change_message(request, actor_name, withdrawn=withdrawn)
    notice = Notice(
        org_id=org_id,
        user_ids={request.user_id},
        category=NotificationCategory.LEAVE_UPDATES,
        slack_text=f"{escape(message)} <{settings.frontend_url}/leave|See details>",
        refresh_request_id=request.id,
        sync_request_id=request.id,
    )
    if request.status == LeaveStatus.REJECTED:
        title = "Approval withdrawn"
    elif withdrawn:
        title = "Leave ended early"
    else:
        title = "Leave changed"
    return stage_rows(
        db,
        notice,
        kind=NotificationType.LEAVE_DECIDED,
        title=title,
        message=message,
        link="/leave",
    )
