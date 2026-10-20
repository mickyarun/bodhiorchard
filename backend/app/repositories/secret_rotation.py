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

"""Every organization, for re-encrypting stored secrets under a new key.

Deliberately not org-scoped: rotating ENCRYPTION_KEY is a maintenance job
run from the command line or at container start, never from a request.
Nothing request-facing may use this repository.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization


class SecretRotationRepository:
    """Cross-org reads of the rows that hold encrypted secrets."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize the repository."""
        self._db = db

    async def all_organizations(self) -> list[Organization]:
        """Every organization (its secret columns and config)."""
        result = await self._db.execute(select(Organization))
        return list(result.scalars().all())
