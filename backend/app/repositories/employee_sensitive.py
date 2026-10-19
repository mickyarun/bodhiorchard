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

"""Data access for employees' sensitive details, documents and access log."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_audit_event import EmployeeAuditAction, EmployeeAuditEvent
from app.models.employee_document import EmployeeDocument
from app.models.employee_sensitive import EmployeeSensitiveDetails
from app.repositories.base import BaseRepository

ACCESS_LOG_LIMIT = 100


class EmployeeSensitiveRepository(BaseRepository[EmployeeSensitiveDetails]):
    """Sensitive detail rows, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(EmployeeSensitiveDetails, db, org_id=org_id)
        self._org = org_id

    async def for_profile(self, profile_id: uuid.UUID) -> EmployeeSensitiveDetails | None:
        """The profile's row, if any details were ever saved."""
        result = await self._db.execute(
            self._scoped(
                select(EmployeeSensitiveDetails).where(
                    EmployeeSensitiveDetails.profile_id == profile_id
                )
            )
        )
        return result.scalar_one_or_none()

    async def for_profile_or_new(self, profile_id: uuid.UUID) -> EmployeeSensitiveDetails:
        """The profile's row, created empty on first save."""
        row = await self.for_profile(profile_id)
        if row is None:
            row = await self.create(
                EmployeeSensitiveDetails(org_id=self._org, profile_id=profile_id)
            )
        return row


class EmployeeDocumentRepository(BaseRepository[EmployeeDocument]):
    """Document rows, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(EmployeeDocument, db, org_id=org_id)

    async def list_for_profile(self, profile_id: uuid.UUID) -> list[EmployeeDocument]:
        """A profile's documents, newest first."""
        result = await self._db.execute(
            self._scoped(
                select(EmployeeDocument).where(EmployeeDocument.profile_id == profile_id)
            ).order_by(EmployeeDocument.created_at.desc())
        )
        return list(result.scalars().all())


class EmployeeAuditRepository:
    """The access log. Deliberately append-only: no update, no delete."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        self._db = db
        self._org = org_id

    def record(
        self,
        *,
        actor_id: uuid.UUID,
        subject_user_id: uuid.UUID,
        profile_id: uuid.UUID,
        action: EmployeeAuditAction,
        target: str,
    ) -> None:
        """Stage one entry in the caller's transaction."""
        self._db.add(
            EmployeeAuditEvent(
                org_id=self._org,
                actor_id=actor_id,
                subject_user_id=subject_user_id,
                profile_id=profile_id,
                action=action,
                target=target,
            )
        )

    async def for_profile(self, profile_id: uuid.UUID) -> list[EmployeeAuditEvent]:
        """The most recent entries about one employee record, newest first."""
        result = await self._db.execute(
            select(EmployeeAuditEvent)
            .where(
                EmployeeAuditEvent.org_id == self._org,
                EmployeeAuditEvent.profile_id == profile_id,
            )
            .order_by(EmployeeAuditEvent.created_at.desc())
            .limit(ACCESS_LOG_LIMIT)
        )
        return list(result.scalars().all())
