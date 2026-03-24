"""User data access repository."""

import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import OrgToUser, User, UserEmailAlias
from app.repositories.base import BaseRepository


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

    def _scoped(self, stmt: Select[tuple[User, ...]]) -> Select[tuple[User, ...]]:
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
        user, membership = row
        user.org_id = membership.org_id  # type: ignore[attr-defined]
        user.role = membership.role  # type: ignore[attr-defined]
        user.role_id = membership.role_id  # type: ignore[attr-defined]
        user.role_ref = membership.role_ref  # type: ignore[attr-defined]
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
            user.org_id = membership.org_id  # type: ignore[attr-defined]
            user.role = membership.role  # type: ignore[attr-defined]
            user.role_id = membership.role_id  # type: ignore[attr-defined]
            user.role_ref = membership.role_ref  # type: ignore[attr-defined]
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
