# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Organization data access repository."""

import uuid

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

    async def get_first_with_claude_api_key(self, auth_mode: str) -> Organization | None:
        """First org configured for ``auth_mode`` with a stored Claude API key."""
        result = await self._db.execute(
            select(Organization)
            .where(Organization.claude_auth_mode == auth_mode)
            .where(Organization.claude_api_key_encrypted.is_not(None))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_with_slack_token_and_config(
        self,
    ) -> list[tuple[uuid.UUID, str, dict | None]]:
        """For every org with a Slack bot token set, return ``(id, encrypted_token, config)``."""
        result = await self._db.execute(
            select(
                Organization.id,
                Organization.slack_bot_token,
                Organization.config,
            ).where(Organization.slack_bot_token.is_not(None))
        )
        return [(row[0], row[1], row[2]) for row in result.all()]

    async def get_slack_bot_token(self, org_id: uuid.UUID) -> str | None:
        """Return the (still-encrypted) Slack bot token for an org, or None."""
        result = await self._db.execute(
            select(Organization.slack_bot_token).where(Organization.id == org_id)
        )
        return result.scalar_one_or_none()

    async def get_config(self, org_id: uuid.UUID) -> dict | None:
        """Return the JSONB ``config`` blob for an org, or None if absent."""
        result = await self._db.execute(
            select(Organization.config).where(Organization.id == org_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slack_team_id(self, team_id: str) -> Organization | None:
        """Fetch an organization by its Slack workspace team_id.

        Args:
            team_id: Slack ``team_id`` (workspace identifier).

        Returns:
            The matching Organization or None.
        """
        result = await self._db.execute(
            select(Organization).where(Organization.slack_team_id == team_id)
        )
        return result.scalar_one_or_none()

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
