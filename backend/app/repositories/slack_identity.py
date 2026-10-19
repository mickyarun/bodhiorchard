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

"""Lookups that keep Slack identities unambiguous.

A member's Slack id doesn't just route messages: it identifies who clicked
Approve in Slack. These checks back the rules that one Slack account maps
to one member, and one Slack workspace to one org.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import OrgToUser, User


class SlackIdentityRepository:
    """Cross-cutting Slack id and team id checks."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize the repository."""
        self._db = db

    async def members_with_slack_id(self, org_id: uuid.UUID, slack_id: str) -> list[uuid.UUID]:
        """Ids of this org's members linked to ``slack_id``."""
        result = await self._db.execute(
            select(User.id)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(OrgToUser.org_id == org_id, User.slack_id == slack_id)
        )
        return list(result.scalars().all())

    async def membership_count(self, user_id: uuid.UUID) -> int:
        """How many orgs ``user_id`` belongs to."""
        result = await self._db.execute(
            select(func.count()).select_from(OrgToUser).where(OrgToUser.user_id == user_id)
        )
        return int(result.scalar() or 0)

    async def team_id_taken(self, team_id: str, org_id: uuid.UUID) -> bool:
        """True if another org already uses this Slack workspace id."""
        result = await self._db.execute(
            select(func.count())
            .select_from(Organization)
            .where(Organization.slack_team_id == team_id, Organization.id != org_id)
        )
        return bool(result.scalar())
