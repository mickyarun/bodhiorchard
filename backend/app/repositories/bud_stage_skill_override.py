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

"""Per-BUD per-stage skill override repository."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDStatus
from app.models.bud_stage_skill_override import BUDStageSkillOverride
from app.repositories.base import BaseRepository


class BUDStageSkillOverrideRepository(BaseRepository[BUDStageSkillOverride]):
    """Repository for per-BUD stage skill overrides, org-scoped."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries.
        """
        super().__init__(BUDStageSkillOverride, db, org_id=org_id)

    async def get_for_bud_and_stage(
        self, bud_id: uuid.UUID, bud_status: BUDStatus
    ) -> BUDStageSkillOverride | None:
        """Return the override (if any) for one BUD at one stage."""
        stmt = self._scoped(
            select(BUDStageSkillOverride)
            .where(BUDStageSkillOverride.bud_id == bud_id)
            .where(BUDStageSkillOverride.bud_status == bud_status)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_bud(self, bud_id: uuid.UUID) -> list[BUDStageSkillOverride]:
        """List all stage overrides recorded for a BUD."""
        stmt = self._scoped(
            select(BUDStageSkillOverride)
            .where(BUDStageSkillOverride.bud_id == bud_id)
            .order_by(BUDStageSkillOverride.bud_status)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def bulk_set_for_bud(
        self,
        bud_id: uuid.UUID,
        overrides: dict[BUDStatus, uuid.UUID],
    ) -> list[BUDStageSkillOverride]:
        """Replace this BUD's overrides with the given (stage → skill_id) map.

        Any stages not present in ``overrides`` are removed. Used by the
        BUD create handler to persist the "Advanced settings" picks in
        one shot.
        """
        await self._db.execute(
            delete(BUDStageSkillOverride)
            .where(BUDStageSkillOverride.org_id == self._org_id)
            .where(BUDStageSkillOverride.bud_id == bud_id)
        )
        rows = [
            BUDStageSkillOverride(
                org_id=self._org_id,
                bud_id=bud_id,
                bud_status=stage,
                skill_id=skill_id,
            )
            for stage, skill_id in overrides.items()
        ]
        for row in rows:
            self._db.add(row)
        await self._db.flush()
        return rows
