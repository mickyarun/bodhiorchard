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

"""Organization data access repository."""

import uuid

from sqlalchemy import select, update
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

    async def get_by_github_app_id(self, app_id: int) -> Organization | None:
        """Fetch an organization by its configured GitHub App ID.

        Used by the install webhook to resolve the target org from
        ``installation`` / ``installation_repositories`` events that have
        no ``repository`` field but always carry ``installation.app_id``.

        Args:
            app_id: Numeric GitHub App ID.

        Returns:
            The matching Organization or None.
        """
        result = await self._db.execute(
            select(Organization).where(Organization.github_app_id == app_id)
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

    async def update_app_slug(self, org_id: uuid.UUID, slug: str) -> None:
        """Persist the GitHub App ``slug`` (lowercase identifier) for an org.

        The slug is back-filled from a one-shot ``GET /app`` call the first
        time we have credentials but no slug. Stored plain text — it
        appears in public install URLs and is not a secret.

        Args:
            org_id: Target organization id.
            slug: Lowercase slug from the GitHub ``/app`` response.
        """
        await self._db.execute(
            update(Organization).where(Organization.id == org_id).values(github_app_slug=slug)
        )

    async def check_setup_exists(self) -> Organization | None:
        """Check if any organization exists (for first-time setup detection).

        Returns:
            The first Organization found, or None if none exist.
        """
        result = await self._db.execute(select(Organization).limit(1))
        return result.scalar_one_or_none()
