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
"""Data access for leave types."""

import uuid
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_type import LeaveType
from app.repositories.base import BaseRepository


class LeaveTypeRepository(BaseRepository[LeaveType]):
    """Leave types, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(LeaveType, db, org_id=org_id)

    async def list_for_policy(
        self, policy_id: uuid.UUID, *, active_only: bool = False
    ) -> list[LeaveType]:
        """A policy's leave types, by name."""
        stmt = self._scoped(select(LeaveType).where(LeaveType.policy_id == policy_id))
        if active_only:
            stmt = stmt.where(LeaveType.is_active.is_(True))
        result = await self._db.execute(stmt.order_by(LeaveType.name))
        return list(result.scalars().all())

    async def code_taken(
        self, policy_id: uuid.UUID, code: str, *, exclude: uuid.UUID | None
    ) -> bool:
        """True if another type on the policy uses ``code``."""
        stmt = self._scoped(
            select(LeaveType.id).where(LeaveType.policy_id == policy_id, LeaveType.code == code)
        )
        if exclude is not None:
            stmt = stmt.where(LeaveType.id != exclude)
        return (await self._db.execute(stmt)).first() is not None

    async def by_ids(self, ids: Collection[uuid.UUID]) -> dict[uuid.UUID, LeaveType]:
        """Rows for ``ids`` in this org, keyed by id."""
        if not ids:
            return {}
        result = await self._db.execute(
            self._scoped(select(LeaveType).where(LeaveType.id.in_(ids)))
        )
        return {row.id: row for row in result.scalars().all()}

    async def list_for_policies(
        self, policy_ids: Collection[uuid.UUID], *, active_only: bool = False
    ) -> dict[uuid.UUID, list[LeaveType]]:
        """Leave types per policy in one query, each list by name."""
        if not policy_ids:
            return {}
        stmt = self._scoped(select(LeaveType).where(LeaveType.policy_id.in_(policy_ids)))
        if active_only:
            stmt = stmt.where(LeaveType.is_active.is_(True))
        out: dict[uuid.UUID, list[LeaveType]] = {pid: [] for pid in policy_ids}
        for row in (await self._db.execute(stmt.order_by(LeaveType.name))).scalars().all():
            out[row.policy_id].append(row)
        return out

    async def with_carry_forward(self) -> list[LeaveType]:
        """Active types that carry unused days into the next leave year."""
        stmt = self._scoped(
            select(LeaveType).where(
                LeaveType.is_active.is_(True), LeaveType.carry_forward_days > 0
            )
        )
        return list((await self._db.execute(stmt)).scalars().all())
