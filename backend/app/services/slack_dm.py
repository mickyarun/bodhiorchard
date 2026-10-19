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

"""Direct messages to members on Slack, in the background.

Best effort: failures are logged and never raised, since the change that
triggered the message is already saved and visible in the app.
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_secret
from app.database import AsyncSessionLocal
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.services.notifications import NotificationCategory, category_default
from app.services.slack_client import chat_post_message, conversations_open

logger = structlog.get_logger(__name__)


async def bot_token(db: AsyncSession, org_id: uuid.UUID) -> str:
    """The org's Slack bot token, or "" when Slack isn't connected."""
    encrypted = await OrganizationRepository(db).get_slack_bot_token(org_id)
    return (decrypt_secret(encrypted) if encrypted else "") or ""


async def send_dm(
    org_id: uuid.UUID, user_ids: set[uuid.UUID], category: NotificationCategory, text: str
) -> None:
    """DM each of ``user_ids`` who hasn't muted ``category``."""
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
    await _deliver(org_id, token, [slack_id for _uid, slack_id in pairs], text)


async def send_security_dm(org_id: uuid.UUID, user_id: uuid.UUID, text: str) -> None:
    """DM a security alert (e.g. bank details changed). It can't be muted."""
    async with AsyncSessionLocal() as session:
        token = await bot_token(session, org_id)
        if not token:
            return
        pairs = await UserRepository(session).list_active_slack_user_pairs(org_id)
    await _deliver(org_id, token, [sid for uid, sid in pairs if uid == user_id], text)


async def _deliver(org_id: uuid.UUID, token: str, slack_ids: list[str], text: str) -> None:
    for slack_id in slack_ids:
        try:
            channel = await conversations_open(token, slack_id)
            if channel:
                await chat_post_message(token, channel, text)
        except Exception:
            logger.warning("slack_dm_failed", org_id=str(org_id), exc_info=True)
