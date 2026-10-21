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

"""Members who let Bodhiorchard set their Slack status."""

import uuid
from datetime import date

from sqlalchemy import Select, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.slack_status_link import SlackStatusLink
from app.models.user import OrgToUser, User
from app.repositories.base import BaseRepository, rowcount


class SlackStatusLinkRepository(BaseRepository[SlackStatusLink]):
    """Links, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(SlackStatusLink, db, org_id=org_id)
        self._org = org_id

    async def save(self, user_id: uuid.UUID, team_id: str, slack_user_id: str, token: str) -> None:
        """Store (or replace) a member's encrypted token; they'll be refreshed next tick."""
        values = {
            "slack_team_id": team_id,
            "slack_user_id": slack_user_id,
            "token": token,
            "refreshed_on": None,
        }
        await self._db.execute(
            insert(SlackStatusLink)
            .values(id=uuid.uuid4(), org_id=self._org, user_id=user_id, **values)
            .on_conflict_do_update(constraint="uq_slack_status_links_org_user", set_=values)
        )

    async def for_user(self, user_id: uuid.UUID) -> SlackStatusLink | None:
        """A member's link, if they connected."""
        result = await self._db.execute(
            self._scoped(select(SlackStatusLink).where(SlackStatusLink.user_id == user_id))
        )
        return result.scalar_one_or_none()

    async def remove(self, user_id: uuid.UUID) -> bool:
        """Forget a member's token; False if there was none."""
        result = await self._db.execute(
            delete(SlackStatusLink).where(
                SlackStatusLink.org_id == self._org, SlackStatusLink.user_id == user_id
            )
        )
        return rowcount(result) > 0

    def _members(self, *, current: bool) -> Select[tuple[SlackStatusLink]]:
        """Links whose member is (or, ``current=False``, no longer is) active here."""
        member = (
            select(OrgToUser.id)
            .join(User, User.id == OrgToUser.user_id)
            .where(
                OrgToUser.org_id == SlackStatusLink.org_id,
                OrgToUser.user_id == SlackStatusLink.user_id,
                User.is_active.is_(True),
            )
            .exists()
        )
        return self._scoped(select(SlackStatusLink)).where(member if current else ~member)

    async def all_links(self) -> list[SlackStatusLink]:
        """Every connected member still active in the org."""
        return list((await self._db.execute(self._members(current=True))).scalars().all())

    async def departed_links(self) -> list[SlackStatusLink]:
        """Links of people removed from the org (or deactivated): to clear and forget."""
        return list((await self._db.execute(self._members(current=False))).scalars().all())

    async def mark_refreshed(self, user_id: uuid.UUID, day: date) -> None:
        """Note the local date a member's status was last set for."""
        await self._db.execute(
            update(SlackStatusLink)
            .where(SlackStatusLink.org_id == self._org, SlackStatusLink.user_id == user_id)
            .values(refreshed_on=day)
        )
