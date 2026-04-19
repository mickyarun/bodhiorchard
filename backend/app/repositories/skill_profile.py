# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""SkillProfile data access repository."""

import uuid

from sqlalchemy import delete as sql_delete
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

    async def delete_all_for_org(self) -> int:
        """Delete all skill profiles for the org (full rescan rebuild).

        Returns:
            Number of rows deleted.
        """
        result = await self._db.execute(
            sql_delete(SkillProfile).where(SkillProfile.org_id == self._org_id)
        )
        return result.rowcount

    async def transfer_profiles(
        self,
        source_user_id: uuid.UUID,
        target_user_id: uuid.UUID,
    ) -> int:
        """Transfer skill profiles from one user to another.

        For each source profile, if the target already has a profile for
        the same module, the source profile is deleted (target's is kept).
        Otherwise, the source profile is re-pointed to the target.

        Args:
            source_user_id: The user being merged away.
            target_user_id: The user to receive profiles.

        Returns:
            Number of profiles transferred.
        """
        # Find modules the target already has
        target_result = await self._db.execute(
            select(SkillProfile.module).where(
                SkillProfile.user_id == target_user_id,
                SkillProfile.org_id == self._org_id,
            )
        )
        target_modules = {row[0] for row in target_result.all()}

        # Get all source profiles
        source_result = await self._db.execute(
            select(SkillProfile).where(
                SkillProfile.user_id == source_user_id,
                SkillProfile.org_id == self._org_id,
            )
        )
        source_profiles = list(source_result.scalars().all())

        transferred = 0
        for profile in source_profiles:
            if profile.module in target_modules:
                # Target already has this module — delete the source duplicate
                await self._db.delete(profile)
            else:
                # Transfer to target
                profile.user_id = target_user_id
                target_modules.add(profile.module)
                transferred += 1

        await self._db.flush()
        return transferred

    async def count_profiles(self) -> int:
        """Count total skill profiles for the organization.

        Returns:
            Number of skill profiles in the organization.
        """
        result = await self._db.execute(
            select(func.count(SkillProfile.id)).where(SkillProfile.org_id == self._org_id)
        )
        return result.scalar() or 0
