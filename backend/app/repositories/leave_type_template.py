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
"""Data access for the org's leave type library."""

import uuid

from sqlalchemy import ColumnElement, SQLColumnExpression, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_type_template import LeaveTypeTemplate
from app.repositories.base import BaseRepository, violated_constraint


class LeaveTypeTemplateRepository(BaseRepository[LeaveTypeTemplate]):
    """Library leave types, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(LeaveTypeTemplate, db, org_id=org_id)

    async def list_by_name(self) -> list[LeaveTypeTemplate]:
        """Every library type in the org, by name."""
        return await self.list_all(order_by=LeaveTypeTemplate.name)

    async def get_for_update(self, template_id: uuid.UUID) -> LeaveTypeTemplate | None:
        """The entry, locked until the transaction ends.

        Edits of an entry, and writes copying it onto a policy's type, then
        happen one after the other: no linked type is left on old rules.
        """
        stmt = self._scoped(
            select(LeaveTypeTemplate).where(LeaveTypeTemplate.id == template_id)
        ).with_for_update()
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def create_unique(self, entry: LeaveTypeTemplate) -> bool:
        """Insert ``entry``; False (nothing added) if its code was taken meanwhile."""
        try:
            async with self._db.begin_nested():
                self._db.add(entry)
                await self._db.flush()
        except IntegrityError as exc:
            if violated_constraint(exc) != "uq_leave_type_templates_org_code":
                raise
            return False
        await self._db.refresh(entry)
        return True

    async def name_taken(self, name: str, *, exclude: uuid.UUID | None) -> bool:
        """True if another library type has ``name``, ignoring case and spacing."""
        stmt = self._scoped(
            select(LeaveTypeTemplate.id).where(
                _name_key(LeaveTypeTemplate.name) == _name_key(name)
            )
        )
        if exclude is not None:
            stmt = stmt.where(LeaveTypeTemplate.id != exclude)
        return (await self._db.execute(stmt)).first() is not None

    async def code_taken(self, code: str, *, exclude: uuid.UUID | None) -> bool:
        """True if another library type uses ``code``."""
        stmt = self._scoped(select(LeaveTypeTemplate.id).where(LeaveTypeTemplate.code == code))
        if exclude is not None:
            stmt = stmt.where(LeaveTypeTemplate.id != exclude)
        return (await self._db.execute(stmt)).first() is not None


def _name_key(name: SQLColumnExpression[str] | str) -> ColumnElement[str]:
    """ "Sick  Leave" and "sick leave" compare equal (as the linking plan matches them)."""
    collapsed = func.regexp_replace(func.btrim(name), r"\s+", " ", "g")
    return func.lower(collapsed)
