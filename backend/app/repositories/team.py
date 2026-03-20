"""Team data access repository."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team, TeamMember
from app.repositories.base import BaseRepository


class TeamRepository(BaseRepository[Team]):
    """Repository for Team queries, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries.
        """
        super().__init__(Team, db, org_id=org_id)

    async def list_teams(self) -> list[Team]:
        """List all teams for the organization.

        Returns:
            List of Team instances with members loaded.
        """
        stmt = self._scoped(select(Team).order_by(Team.name))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_with_members(self, team_id: uuid.UUID) -> Team | None:
        """Fetch a single team by ID with its members.

        Args:
            team_id: The team UUID.

        Returns:
            The Team or None.
        """
        stmt = self._scoped(select(Team).where(Team.id == team_id))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def add_member(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str = "member",
    ) -> TeamMember:
        """Add a user to a team.

        Args:
            team_id: The team UUID.
            user_id: The user UUID.
            role: Member role ("lead" or "member").

        Returns:
            The created TeamMember.
        """
        member = TeamMember(team_id=team_id, user_id=user_id, role=role)
        self._db.add(member)
        await self._db.flush()
        return member

    async def remove_member(self, team_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Remove a user from a team.

        Args:
            team_id: The team UUID.
            user_id: The user UUID.

        Returns:
            True if a member was removed, False if not found.
        """
        result = await self._db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if member is None:
            return False
        await self._db.delete(member)
        await self._db.flush()
        return True
