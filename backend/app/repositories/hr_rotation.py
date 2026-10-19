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

"""Every encrypted HR row across all orgs, for key rotation only.

Deliberately not org-scoped: rotating the platform's HR key is a
maintenance job run by an operator from the command line, never from a
request. Nothing request-facing may use this repository.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_document import EmployeeDocument
from app.models.employee_sensitive import EmployeeSensitiveDetails


class HRRotationRepository:
    """Cross-org reads of encrypted rows."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize the repository."""
        self._db = db

    async def all_sensitive(self) -> list[EmployeeSensitiveDetails]:
        """Every sensitive details row."""
        result = await self._db.execute(select(EmployeeSensitiveDetails))
        return list(result.scalars().all())

    async def all_documents(self) -> list[EmployeeDocument]:
        """Every document row."""
        result = await self._db.execute(select(EmployeeDocument))
        return list(result.scalars().all())
