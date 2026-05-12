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

"""User data access repository."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Select, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.developer_xp import DeveloperXP
from app.models.skill_profile import SkillProfile
from app.models.user import OrgToUser, User, UserEmailAlias, UserRole
from app.repositories.base import BaseRepository, SelectT

if TYPE_CHECKING:
    from app.models.user import UserRole


class UserRepository(BaseRepository[User]):
    """Repository for User queries, optionally scoped to an organization.

    When org_id is provided, queries join through OrgToUser to filter
    by organization membership.
    """

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID | None = None) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Optional organization UUID for scoping queries.
        """
        super().__init__(User, db, org_id=org_id)

    def _scoped(self, stmt: Select[SelectT]) -> Select[SelectT]:
        """Apply tenant scope by joining OrgToUser when org_id is set."""
        if self._org_id is not None:
            stmt = stmt.join(OrgToUser, OrgToUser.user_id == User.id).where(
                OrgToUser.org_id == self._org_id
            )
        return stmt

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a user by email within the scoped organization.

        Args:
            email: The email address to search for.

        Returns:
            The matching User or None.
        """
        stmt = self._scoped(select(User).where(User.email == email))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email_in_org(self, org_id: uuid.UUID, email: str) -> User | None:
        """Fetch a user by email in a specific organization.

        Args:
            org_id: The organization UUID to search within.
            email: The email address to search for.

        Returns:
            The matching User or None.
        """
        result = await self._db.execute(
            select(User)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(OrgToUser.org_id == org_id, User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id_in_org(self, user_id: uuid.UUID, org_id: uuid.UUID) -> User | None:
        """Fetch a user by ID if they are a member of the given organization.

        Args:
            user_id: The user UUID.
            org_id: The organization UUID.

        Returns:
            The matching User or None if not found or not a member.
        """
        result = await self._db.execute(
            select(User)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(User.id == user_id, OrgToUser.org_id == org_id)
        )
        return result.scalar_one_or_none()

    async def list_active_slack_user_pairs(self, org_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
        """``(user_id, slack_id)`` pairs for active org members with a slack_id."""
        stmt = (
            select(User.id, User.slack_id)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(
                OrgToUser.org_id == org_id,
                User.slack_id.is_not(None),
                User.is_active.is_(True),
            )
        )
        result = await self._db.execute(stmt)
        return [(row[0], row[1]) for row in result.all() if row[1]]

    async def get_by_slack_id_with_role(
        self, org_id: uuid.UUID, slack_id: str
    ) -> tuple[User, "UserRole | None"] | None:
        """Look up an org member by Slack ID and return ``(user, role)``."""
        stmt = (
            select(User, OrgToUser.role)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(
                OrgToUser.org_id == org_id,
                User.slack_id == slack_id,
            )
        )
        result = await self._db.execute(stmt)
        row = result.one_or_none()
        if row is None:
            return None
        return (row[0], row[1])

    async def list_active_with_role(self, org_id: uuid.UUID, role: UserRole) -> list[User]:
        """Active org members whose ``OrgToUser.role`` equals ``role``."""
        stmt = (
            select(User)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(
                OrgToUser.org_id == org_id,
                OrgToUser.role == role,
                User.is_active == true(),
            )
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_id_by_github_login(
        self, org_id: uuid.UUID, github_login: str
    ) -> uuid.UUID | None:
        """Resolve a GitHub login to a user_id within an org. None if no match."""
        if not github_login:
            return None
        stmt = (
            select(User.id)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(User.github_username == github_login, OrgToUser.org_id == org_id)
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_role(self, user_id: uuid.UUID, org_id: uuid.UUID) -> UserRole | None:
        """Return the user's ``OrgToUser.role`` value within the org, or ``None``."""
        stmt = select(OrgToUser.role).where(
            OrgToUser.user_id == user_id,
            OrgToUser.org_id == org_id,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_first_member_id(self, org_id: uuid.UUID) -> uuid.UUID | None:
        """Return any one user_id from ``OrgToUser`` for the given org, else None."""
        stmt = select(OrgToUser.user_id).where(OrgToUser.org_id == org_id).limit(1)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def map_emails_to_ids(self, org_id: uuid.UUID, emails: set[str]) -> dict[str, uuid.UUID]:
        """Bulk-resolve emails to user_ids within an org.

        Returns lowercase ``email -> user_id`` for matches.
        """
        if not emails:
            return {}
        stmt = (
            select(User.email, User.id)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(OrgToUser.org_id == org_id)
            .where(User.email.in_(emails))
        )
        result = await self._db.execute(stmt)
        return {row[0].lower(): row[1] for row in result.all()}

    async def list_active_members_for_tree(
        self, org_id: uuid.UUID, *, limit: int = 50
    ) -> list[Any]:
        """Heavy aggregate row used by the dashboard tree's member section.

        Joins ``OrgToUser`` (membership), ``SkillProfile`` (touch totals),
        and ``DeveloperXP`` (level/house). Returns rows with attributes
        ``id``, ``name``, ``email``, ``avatar_url``, ``character_model``,
        ``slack_id``, ``total_touches``, ``level``, ``level_name``,
        ``house_level``. Ordered by ``User.id`` to match the Colyseus
        snapshot's slot assignment.
        """
        stmt = (
            select(
                User.id,
                User.name,
                User.email,
                User.avatar_url,
                User.character_model,
                User.slack_id,
                func.coalesce(func.sum(SkillProfile.touch_count), 0).label("total_touches"),
                DeveloperXP.level,
                DeveloperXP.level_name,
                DeveloperXP.house_level,
            )
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .outerjoin(
                SkillProfile,
                (SkillProfile.user_id == User.id) & (SkillProfile.org_id == org_id),
            )
            .outerjoin(
                DeveloperXP,
                (DeveloperXP.user_id == User.id) & (DeveloperXP.org_id == org_id),
            )
            .where(OrgToUser.org_id == org_id)
            .where(User.is_active.is_(True))
            .where(~User.name.ilike("%[bot]%"))
            .group_by(
                User.id,
                User.name,
                User.email,
                User.avatar_url,
                User.character_model,
                User.slack_id,
                DeveloperXP.level,
                DeveloperXP.level_name,
                DeveloperXP.house_level,
            )
            .order_by(User.id)
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.all())

    async def list_active_member_xp_summary(
        self, org_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str | None, str | None, int | None, str | None]]:
        """For each active, non-bot org member return ``(id, name,
        avatar_url, level, level_name)`` ordered by name.

        Used by the standup service which only needs the level summary,
        not the full DeveloperXP row.
        """
        stmt = (
            select(
                User.id,
                User.name,
                User.avatar_url,
                DeveloperXP.level,
                DeveloperXP.level_name,
            )
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .outerjoin(
                DeveloperXP,
                (DeveloperXP.user_id == User.id) & (DeveloperXP.org_id == org_id),
            )
            .where(OrgToUser.org_id == org_id)
            .where(User.is_active.is_(True))
            .where(~User.name.ilike("%[bot]%"))
            .order_by(User.name)
        )
        result = await self._db.execute(stmt)
        return [
            (row.id, row.name, row.avatar_url, row.level, row.level_name) for row in result.all()
        ]

    async def is_member_of_org(self, user_id: uuid.UUID, org_id: uuid.UUID) -> bool:
        """Return True if the user has an OrgToUser membership in the org."""
        result = await self._db.execute(
            select(OrgToUser.user_id).where(
                OrgToUser.org_id == org_id,
                OrgToUser.user_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def list_active_members_with_xp(
        self, org_id: uuid.UUID
    ) -> list[tuple[User, DeveloperXP | None]]:
        """Active org members (excluding bots) with their XP rows.

        Stable ordering by ``user.id`` so callers (e.g. Colyseus snapshot)
        get deterministic slot assignment across reloads.
        """
        stmt = (
            select(User, DeveloperXP)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .outerjoin(
                DeveloperXP,
                (DeveloperXP.user_id == User.id) & (DeveloperXP.org_id == org_id),
            )
            .where(OrgToUser.org_id == org_id)
            .where(User.is_active.is_(True))
            .where(~User.name.ilike("%[bot]%"))
            .order_by(User.id)
        )
        result = await self._db.execute(stmt)
        return list(result.tuples().all())

    async def get_by_slack_id_in_org(self, org_id: uuid.UUID, slack_id: str) -> User | None:
        """Fetch the org member whose ``slack_id`` matches.

        Args:
            org_id: Organization UUID for membership scoping.
            slack_id: Slack user ID to look up.

        Returns:
            The matching User or None.
        """
        result = await self._db.execute(
            select(User)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(OrgToUser.org_id == org_id, User.slack_id == slack_id)
        )
        return result.scalar_one_or_none()

    async def get_membership(self, user_id: uuid.UUID, org_id: uuid.UUID) -> OrgToUser | None:
        """Fetch the OrgToUser membership row for a user/org pair.

        Args:
            user_id: The user UUID.
            org_id: The organization UUID.

        Returns:
            The OrgToUser row, or None if the user is not a member.
        """
        result = await self._db.execute(
            select(OrgToUser).where(
                OrgToUser.user_id == user_id,
                OrgToUser.org_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_slack_id_to_name(self, org_id: uuid.UUID, slack_ids: set[str]) -> dict[str, str]:
        """Map Slack user IDs to Bodhiorchard user display names within an org.

        Args:
            org_id: Organization UUID for membership scoping.
            slack_ids: Set of Slack user IDs to resolve.

        Returns:
            Dict of slack_id → user.name (only entries with both fields).
        """
        if not slack_ids:
            return {}
        stmt = (
            select(User.slack_id, User.name)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(
                OrgToUser.org_id == org_id,
                User.slack_id.in_(slack_ids),
            )
        )
        result = await self._db.execute(stmt)
        return {row.slack_id: row.name for row in result.all() if row.slack_id and row.name}

    async def get_names_by_ids(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Batch-fetch user names by IDs.

        Args:
            user_ids: Set of user UUIDs to look up.

        Returns:
            Dict mapping user_id to user name.
        """
        if not user_ids:
            return {}
        result = await self._db.execute(select(User.id, User.name).where(User.id.in_(user_ids)))
        return {row.id: row.name for row in result.all()}

    async def list_by_org(self, org_id: uuid.UUID) -> list[User]:
        """List all users in a given organization.

        Args:
            org_id: The organization UUID.

        Returns:
            List of User instances belonging to the organization.
        """
        result = await self._db.execute(
            select(User)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(OrgToUser.org_id == org_id)
        )
        return list(result.scalars().all())

    async def get_by_id_with_membership(
        self, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> User | None:
        """Load a user and set transient org/role attrs from OrgToUser.

        Args:
            user_id: The user UUID.
            org_id: The organization UUID.

        Returns:
            User with org_id, role, role_id, role_ref set, or None.
        """
        result = await self._db.execute(
            select(User, OrgToUser)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(User.id == user_id, OrgToUser.org_id == org_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        user: User = row[0]
        membership: OrgToUser = row[1]
        user.org_id = membership.org_id
        user.role = membership.role
        user.role_id = membership.role_id
        user.role_ref = membership.role_ref
        return user

    async def list_with_membership(self, org_id: uuid.UUID) -> list[User]:
        """List users in an org with transient role attrs set from OrgToUser.

        Args:
            org_id: The organization UUID.

        Returns:
            List of User instances with org_id, role, role_id, role_ref set.
        """
        result = await self._db.execute(
            select(User, OrgToUser)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(OrgToUser.org_id == org_id)
        )
        users = []
        for user, membership in result.all():
            user.org_id = membership.org_id
            user.role = membership.role
            user.role_id = membership.role_id
            user.role_ref = membership.role_ref
            users.append(user)
        return users

    async def get_email_map(self, org_id: uuid.UUID) -> dict[str, User]:
        """Build a lowercase-email to User mapping for an organization.

        Includes both primary emails and email aliases, so git commits
        authored with any known email resolve to the correct user.

        Args:
            org_id: The organization UUID.

        Returns:
            Dict mapping lowercase email strings to User instances.
        """
        users = await self.list_by_org(org_id)
        email_map = {u.email.lower(): u for u in users}

        # Add aliases
        user_by_id = {u.id: u for u in users}
        result = await self._db.execute(
            select(UserEmailAlias).where(UserEmailAlias.org_id == org_id)
        )
        for alias in result.scalars():
            user = user_by_id.get(alias.user_id)
            if user:
                email_map[alias.email.lower()] = user

        return email_map

    async def add_email_alias(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        email: str,
    ) -> UserEmailAlias | None:
        """Add an email alias for a user. Skips if already exists.

        Args:
            org_id: Organization UUID.
            user_id: Target user UUID.
            email: The alias email.

        Returns:
            The created alias, or None if it already exists.
        """
        existing = await self._db.execute(
            select(UserEmailAlias).where(
                UserEmailAlias.org_id == org_id,
                UserEmailAlias.email == email,
            )
        )
        if existing.scalar_one_or_none():
            return None
        alias = UserEmailAlias(user_id=user_id, org_id=org_id, email=email)
        self._db.add(alias)
        return alias

    async def list_aliases(self, user_id: uuid.UUID) -> list[UserEmailAlias]:
        """List all email aliases for a user.

        Args:
            user_id: The user UUID.

        Returns:
            List of alias records.
        """
        result = await self._db.execute(
            select(UserEmailAlias).where(UserEmailAlias.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_alias_map_for_org(
        self,
        org_id: uuid.UUID,
    ) -> dict[uuid.UUID, list[str]]:
        """Build a user_id → [alias emails] mapping for an entire org.

        Single query instead of per-user lookups.

        Args:
            org_id: The organization UUID.

        Returns:
            Dict mapping user UUIDs to lists of alias email strings.
        """
        result = await self._db.execute(
            select(UserEmailAlias).where(UserEmailAlias.org_id == org_id)
        )
        alias_map: dict[uuid.UUID, list[str]] = {}
        for alias in result.scalars():
            alias_map.setdefault(alias.user_id, []).append(alias.email)
        return alias_map
