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

"""Data access for leave policies."""

import uuid
from collections.abc import Collection

from sqlalchemy import delete as sql_delete
from sqlalchemy import exists, select
from sqlalchemy import update as sql_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeProfile
from app.models.leave_ledger import LeaveLedgerEntry
from app.models.leave_policy import LeavePolicy
from app.models.leave_request import LeaveRequest
from app.models.leave_type import LeaveType
from app.repositories.base import BaseRepository


class LeavePolicyRepository(BaseRepository[LeavePolicy]):
    """Leave policies, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Tenant whose policies this repository exposes.
        """
        super().__init__(LeavePolicy, db, org_id=org_id)
        self._org = org_id

    async def list_ordered(self) -> list[LeavePolicy]:
        """Default policy first, then by name."""
        result = await self._db.execute(
            self._scoped(select(LeavePolicy)).order_by(
                LeavePolicy.is_default.desc(), LeavePolicy.name
            )
        )
        return list(result.scalars().all())

    async def get_default(self) -> LeavePolicy | None:
        """The org's default policy, if one exists."""
        result = await self._db.execute(
            self._scoped(select(LeavePolicy).where(LeavePolicy.is_default.is_(True)))
        )
        return result.scalar_one_or_none()

    async def create_default(self, policy: LeavePolicy) -> LeavePolicy:
        """Insert the org's default policy, or return the one a racer created.

        The Leave page loads several endpoints at once, and each may find no
        default and try to create it. The insert runs in a savepoint; the
        loser of the race rolls back just that and reads the winner's row.
        """
        try:
            async with self._db.begin_nested():
                self._db.add(policy)
                await self._db.flush()
        except IntegrityError:
            existing = await self.get_default()
            if existing is None:
                raise
            return existing
        await self._db.refresh(policy)
        return policy

    async def clear_default(self) -> None:
        """Unset the default flag (before setting a new default)."""
        await self._db.execute(
            sql_update(LeavePolicy)
            .where(LeavePolicy.org_id == self._org, LeavePolicy.is_default.is_(True))
            .values(is_default=False)
        )
        await self._db.flush()

    async def name_taken(self, name: str, *, exclude: uuid.UUID | None) -> bool:
        """True if another policy in this org uses ``name``."""
        stmt = self._scoped(select(LeavePolicy.id).where(LeavePolicy.name == name))
        if exclude is not None:
            stmt = stmt.where(LeavePolicy.id != exclude)
        return (await self._db.execute(stmt)).first() is not None

    async def has_requests(self, policy_id: uuid.UUID) -> bool:
        """True once any request was made under the policy."""
        stmt = select(
            exists().where(LeaveRequest.org_id == self._org, LeaveRequest.policy_id == policy_id)
        )
        return bool((await self._db.execute(stmt)).scalar())

    async def has_people(self, policy_id: uuid.UUID) -> bool:
        """True if any employee is explicitly assigned to the policy."""
        stmt = select(
            exists().where(
                EmployeeProfile.org_id == self._org, EmployeeProfile.leave_policy_id == policy_id
            )
        )
        return bool((await self._db.execute(stmt)).scalar())

    async def has_balance_history(self, policy_id: uuid.UUID) -> bool:
        """True if any allocation or adjustment was booked on the policy's types."""
        stmt = select(
            exists().where(
                LeaveLedgerEntry.org_id == self._org,
                LeaveLedgerEntry.leave_type_id == LeaveType.id,
                LeaveType.policy_id == policy_id,
            )
        )
        return bool((await self._db.execute(stmt)).scalar())

    async def delete_with_types(self, policy: LeavePolicy) -> None:
        """Delete a policy and its leave types (its holidays go by cascade).

        Only for a policy with no people, requests or balance history: the
        caller checks, since those must outlive a policy.
        """
        await self._db.execute(
            sql_delete(LeaveType).where(
                LeaveType.org_id == self._org, LeaveType.policy_id == policy.id
            )
        )
        await self.delete(policy)

    async def by_ids(self, ids: Collection[uuid.UUID]) -> dict[uuid.UUID, LeavePolicy]:
        """Policies for ``ids`` in this org, keyed by id."""
        if not ids:
            return {}
        result = await self._db.execute(
            self._scoped(select(LeavePolicy).where(LeavePolicy.id.in_(ids)))
        )
        return {row.id: row for row in result.scalars().all()}
