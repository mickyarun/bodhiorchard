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

"""Data access for office locations."""

import uuid
from collections.abc import Collection

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeProfile
from app.models.office_location import OfficeLocation
from app.repositories.base import BaseRepository


class OfficeLocationRepository(BaseRepository[OfficeLocation]):
    """Offices, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(OfficeLocation, db, org_id=org_id)
        self._org = org_id

    async def list_with_counts(self) -> list[tuple[OfficeLocation, int]]:
        """Every office, by name, with how many people work there."""
        people = (
            select(func.count(EmployeeProfile.id))
            .where(
                EmployeeProfile.org_id == self._org,
                EmployeeProfile.office_id == OfficeLocation.id,
            )
            .scalar_subquery()
        )
        result = await self._db.execute(
            self._scoped(select(OfficeLocation, people)).order_by(OfficeLocation.name)
        )
        return [(row[0], int(row[1])) for row in result.all()]

    async def by_ids(self, ids: Collection[uuid.UUID]) -> dict[uuid.UUID, OfficeLocation]:
        """Offices for ``ids`` in this org, keyed by id."""
        if not ids:
            return {}
        result = await self._db.execute(
            self._scoped(select(OfficeLocation).where(OfficeLocation.id.in_(ids)))
        )
        return {row.id: row for row in result.scalars().all()}

    async def name_taken(self, name: str, *, exclude: uuid.UUID | None) -> bool:
        """True if another office in this org has ``name`` (any case)."""
        stmt = self._scoped(
            select(OfficeLocation.id).where(func.lower(OfficeLocation.name) == name.lower())
        )
        if exclude is not None:
            stmt = stmt.where(OfficeLocation.id != exclude)
        return (await self._db.execute(stmt.limit(1))).first() is not None

    async def has_people(self, office_id: uuid.UUID) -> bool:
        """True if anyone works from the office."""
        stmt = select(
            exists().where(
                EmployeeProfile.org_id == self._org, EmployeeProfile.office_id == office_id
            )
        )
        return bool((await self._db.execute(stmt)).scalar())
