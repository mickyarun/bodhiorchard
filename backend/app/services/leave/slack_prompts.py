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

"""Leave messages on Slack: plain DMs, approval prompts with buttons, and
closing those prompts once a request is decided.

Both run in the background on their own session, after the change that
triggered them has committed. Slack failures are logged and swallowed:
the request itself is already saved and visible in the app.
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.encryption import decrypt_secret
from app.database import AsyncSessionLocal
from app.models.leave_request import LeaveRequest, LeaveStatus
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.leave_slack_prompt import LeaveSlackPromptRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.services.leave.messages import compose_request_message
from app.services.leave.slack_blocks import approval_blocks, escape, outcome_blocks
from app.services.notifications import NotificationCategory, category_default
from app.services.slack_client import chat_post_message, conversations_open
from app.services.slack_interactive import post_message, update_message

logger = structlog.get_logger(__name__)


async def bot_token(db: AsyncSession, org_id: uuid.UUID) -> str:
    """The org's Slack bot token, or "" when Slack isn't connected."""
    encrypted = await OrganizationRepository(db).get_slack_bot_token(org_id)
    return (decrypt_secret(encrypted) if encrypted else "") or ""


async def send_dm(
    org_id: uuid.UUID, user_ids: set[uuid.UUID], category: NotificationCategory, text: str
) -> None:
    """A plain DM to each of ``user_ids`` who allows ``category``."""
    async with AsyncSessionLocal() as session:
        token = await bot_token(session, org_id)
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


async def send_prompts(
    org_id: uuid.UUID, request_id: uuid.UUID, approver_ids: set[uuid.UUID], text: str
) -> None:
    """DM each approver who allows it the request with Approve / Reject buttons."""
    async with AsyncSessionLocal() as db:
        token = await bot_token(db, org_id)
        if not token:
            return
        pairs = await UserRepository(db).list_slack_recipients(
            org_id,
            category=NotificationCategory.LEAVE_APPROVALS,
            default_enabled=category_default(NotificationCategory.LEAVE_APPROVALS),
            user_ids=approver_ids,
        )
        blocks = approval_blocks(text, request_id, f"{settings.frontend_url}/leave/approvals")
        prompts = LeaveSlackPromptRepository(db, org_id=org_id)
        for user_id, slack_id in pairs:
            try:
                dm = await conversations_open(token, slack_id)
                if not dm:
                    continue
                channel, ts, error = await post_message(token, dm, escape(text), blocks)
                if not error:
                    await prompts.remember(request_id, user_id, channel, ts)
            except Exception:
                # One approver's DM failing mustn't stop the others.
                logger.warning("leave_slack_prompt_failed", org_id=str(org_id), exc_info=True)
        await db.commit()
    # It may have been decided while the DMs were going out.
    await refresh_prompts(org_id, request_id)


async def refresh_prompts(org_id: uuid.UUID, request_id: uuid.UUID) -> None:
    """Swap the buttons for the outcome on every prompt, once it's decided."""
    async with AsyncSessionLocal() as db:
        request = await LeaveRequestRepository(db, org_id=org_id).get_by_id(request_id)
        if request is None or request.status == LeaveStatus.PENDING:
            return
        prompts = await LeaveSlackPromptRepository(db, org_id=org_id).for_request(request_id)
        if not prompts:
            return
        token = await bot_token(db, org_id)
        if not token:
            return
        people = {request.user_id} | ({request.decided_by} if request.decided_by else set())
        names = await UserRepository(db).get_names_by_ids(people)
    text = compose_request_message(
        names.get(request.user_id, "Someone"), request, auto_approved=False
    )
    blocks = outcome_blocks(text, outcome_line(request, names))
    for prompt in prompts:
        await update_message(token, prompt.channel, prompt.ts, escape(text), blocks)


def outcome_line(request: LeaveRequest, names: dict[uuid.UUID, str]) -> str:
    """ "Approved by Priya", "Rejected by Priya" or "Cancelled by Ravi"."""
    decider = names.get(request.decided_by, "someone") if request.decided_by else "someone"
    if request.status == LeaveStatus.APPROVED:
        return f"Approved by {decider}"
    if request.status == LeaveStatus.REJECTED:
        return f"Rejected by {decider}"
    return f"Cancelled by {names.get(request.user_id, 'the requester')}"
