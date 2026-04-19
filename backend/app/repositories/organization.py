# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Organization data access repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import User
from app.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    """Repository for Organization queries. No org_id scope -- Organization IS the tenant."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
        """
        super().__init__(Organization, db)

    async def get_by_slug(self, slug: str) -> Organization | None:
        """Fetch an organization by its unique slug.

        Args:
            slug: The organization slug to look up.

        Returns:
            The matching Organization or None.
        """
        result = await self._db.execute(select(Organization).where(Organization.slug == slug))
        return result.scalar_one_or_none()

    async def get_for_user(self, user: User) -> Organization:
        """Load the active organization for an authenticated user.

        The user must have been loaded via get_current_user so that the
        transient org_id attribute is set from the JWT.

        Args:
            user: The authenticated user with org_id set.

        Returns:
            The user's active Organization.

        Raises:
            NoResultFound: If no organization matches.
        """
        result = await self._db.execute(select(Organization).where(Organization.id == user.org_id))
        return result.scalar_one()

    async def get_all_with_mcp_tokens(self) -> list[Organization]:
        """Fetch all organizations that have an MCP token hash set.

        Returns:
            List of Organizations with a non-null mcp_token_hash.
        """
        result = await self._db.execute(
            select(Organization).where(Organization.mcp_token_hash.is_not(None))
        )
        return list(result.scalars().all())

    async def check_setup_exists(self) -> Organization | None:
        """Check if any organization exists (for first-time setup detection).

        Returns:
            The first Organization found, or None if none exist.
        """
        result = await self._db.execute(select(Organization).limit(1))
        return result.scalar_one_or_none()
