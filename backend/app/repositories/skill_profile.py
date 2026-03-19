"""SkillProfile data access repository."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill_profile import SkillProfile
from app.models.user import User
from app.repositories.base import BaseRepository


class SkillProfileRepository(BaseRepository[SkillProfile]):
    """Repository for SkillProfile queries, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries.
        """
        super().__init__(SkillProfile, db, org_id=org_id)

    async def list_with_users(self) -> list[tuple[SkillProfile, User]]:
        """List skill profiles with their associated users, ordered by score.

        Returns:
            List of (SkillProfile, User) tuples sorted by skill_score descending.
                User may be None for orphaned profiles.
        """
        result = await self._db.execute(
            select(SkillProfile, User)
            .outerjoin(User, SkillProfile.user_id == User.id)
            .where(SkillProfile.org_id == self._org_id)
            .order_by(SkillProfile.skill_score.desc())
        )
        return list(result.all())

    async def get_by_user_and_module(
        self,
        user_id: uuid.UUID,
        module: str,
    ) -> SkillProfile | None:
        """Fetch a skill profile by user and module name.

        Args:
            user_id: The user UUID.
            module: The module/component name.

        Returns:
            The matching SkillProfile or None.
        """
        result = await self._db.execute(
            select(SkillProfile).where(
                SkillProfile.user_id == user_id,
                SkillProfile.org_id == self._org_id,
                SkillProfile.module == module,
            )
        )
        return result.scalar_one_or_none()

    async def count_profiles(self) -> int:
        """Count total skill profiles for the organization.

        Returns:
            Number of skill profiles in the organization.
        """
        result = await self._db.execute(
            select(func.count(SkillProfile.id)).where(SkillProfile.org_id == self._org_id)
        )
        return result.scalar() or 0
