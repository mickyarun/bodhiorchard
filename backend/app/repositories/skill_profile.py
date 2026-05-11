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
        """List feature-mapped skill profiles with their users, ordered by score.

        Phase E seeds rows keyed by directory (``src``, ``kube``, …) with
        ``feature_id`` NULL; Phase E2 sets ``feature_id`` only on rows whose
        files matched a feature's ``code_locations``. The Skills UI and the
        ``get_team_context`` MCP tool both surface "developer-skill-as-feature",
        so unmapped rows are excluded here. Routing / estimation / admin
        paths use different repo methods and intentionally see all rows.
        """
        result = await self._db.execute(
            select(SkillProfile, User)
            .outerjoin(User, SkillProfile.user_id == User.id)
            .where(SkillProfile.org_id == self._org_id)
            .where(SkillProfile.feature_id.is_not(None))
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

    async def list_modules_for_users(
        self, user_ids: list[uuid.UUID]
    ) -> list[tuple[uuid.UUID, str, float]]:
        """``(user_id, module, skill_score)`` rows for the given users in this org,
        ordered by user then by score descending.
        """
        if not user_ids:
            return []
        stmt = self._scoped(
            select(SkillProfile.user_id, SkillProfile.module, SkillProfile.skill_score)
            .where(SkillProfile.user_id.in_(user_ids))
            .order_by(SkillProfile.user_id, SkillProfile.skill_score.desc())
        )
        result = await self._db.execute(stmt)
        return [(row.user_id, row.module, row.skill_score) for row in result.all()]

    async def list_for_user(self, user_id: uuid.UUID) -> list[SkillProfile]:
        """All skill profile rows for a user within the scoped org."""
        stmt = self._scoped(select(SkillProfile).where(SkillProfile.user_id == user_id))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_users(self, user_ids: list[uuid.UUID]) -> list[SkillProfile]:
        """All skill profile rows for the given users in this org."""
        if not user_ids:
            return []
        stmt = self._scoped(select(SkillProfile).where(SkillProfile.user_id.in_(user_ids)))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_active_skill_devs(
        self, *, min_skill_score: float = 0.1
    ) -> list[tuple[str, uuid.UUID, float, uuid.UUID | None, str]]:
        """``(module, user_id, skill_score, feature_id, dev_name)`` for active
        skill rows whose score exceeds ``min_skill_score``, sorted by score desc.
        """
        stmt = self._scoped(
            select(
                SkillProfile.module,
                SkillProfile.user_id,
                SkillProfile.skill_score,
                SkillProfile.feature_id,
                User.name.label("dev_name"),
            )
            .join(User, User.id == SkillProfile.user_id)
            .where(SkillProfile.skill_score > min_skill_score)
            .where(User.is_active.is_(True))
            .order_by(SkillProfile.skill_score.desc())
        )
        result = await self._db.execute(stmt)
        return [
            (row.module, row.user_id, row.skill_score, row.feature_id, row.dev_name)
            for row in result.all()
        ]
