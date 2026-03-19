"""User data access repository."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User queries, optionally scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID | None = None) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Optional organization UUID for scoping queries.
        """
        super().__init__(User, db, org_id=org_id)

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
        """Fetch a user by email in a specific organization (ignoring scope).

        Args:
            org_id: The organization UUID to search within.
            email: The email address to search for.

        Returns:
            The matching User or None.
        """
        result = await self._db.execute(
            select(User).where(User.org_id == org_id, User.email == email)
        )
        return result.scalar_one_or_none()

    async def list_by_org(self, org_id: uuid.UUID) -> list[User]:
        """List all users in a given organization.

        Args:
            org_id: The organization UUID.

        Returns:
            List of User instances belonging to the organization.
        """
        result = await self._db.execute(select(User).where(User.org_id == org_id))
        return list(result.scalars().all())

    async def get_email_map(self, org_id: uuid.UUID) -> dict[str, User]:
        """Build a lowercase-email to User mapping for an organization.

        Args:
            org_id: The organization UUID.

        Returns:
            Dict mapping lowercase email strings to User instances.
        """
        users = await self.list_by_org(org_id)
        return {u.email.lower(): u for u in users}
