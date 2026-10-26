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

"""The few Slack status lookups that look across orgs, on purpose.

A Slack account has one status, so only one org may drive it; finding the
other org's link for the same account, and which orgs to visit, are the
only cross-org reads. Nothing here returns another org's leave.

An account is matched on the Slack user id alone: ids are unique across
Slack, and an Enterprise Grid member keeps one id (and one status) in every
workspace of the enterprise, so the workspace id can't tell accounts apart.
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.slack_status_link import SlackStatusLink
from app.repositories.base import rowcount

STATUS_SECTION = "slack_status"


class SlackStatusAccountRepository:
    """Cross-org reads and the one cross-org delete (handing an account over)."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize the repository."""
        self._db = db

    async def orgs_with_status_on(self) -> list[uuid.UUID]:
        """Orgs whose HR switched Slack status on (with or without a bot token)."""
        enabled = Organization.config[STATUS_SECTION]["enabled"].as_boolean()
        result = await self._db.execute(select(Organization.id).where(enabled.is_(True)))
        return list(result.scalars().all())

    async def orgs_with_links(self) -> list[uuid.UUID]:
        """Orgs holding any member's token (swept for people who left, even when off)."""
        result = await self._db.execute(select(SlackStatusLink.org_id).distinct())
        return list(result.scalars().all())

    async def links_for_account(self, slack_user_id: str) -> list[SlackStatusLink]:
        """Every org's link for this Slack account."""
        result = await self._db.execute(
            select(SlackStatusLink).where(SlackStatusLink.slack_user_id == slack_user_id)
        )
        return list(result.scalars().all())

    async def links_elsewhere(
        self, slack_user_id: str, org_id: uuid.UUID
    ) -> list[SlackStatusLink]:
        """Other orgs' links for the same Slack account."""
        result = await self._db.execute(
            select(SlackStatusLink).where(
                SlackStatusLink.slack_user_id == slack_user_id,
                SlackStatusLink.org_id != org_id,
            )
        )
        return list(result.scalars().all())

    async def remove_elsewhere(self, slack_user_id: str, org_id: uuid.UUID) -> int:
        """Drop other orgs' links for the account now driven by ``org_id``."""
        result = await self._db.execute(
            delete(SlackStatusLink).where(
                SlackStatusLink.slack_user_id == slack_user_id,
                SlackStatusLink.org_id != org_id,
            )
        )
        return rowcount(result)
