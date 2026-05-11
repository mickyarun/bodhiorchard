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

"""Repository for QA test evidence CRUD operations."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qa_test_evidence import QATestEvidence
from app.repositories.base import BaseRepository


class QATestEvidenceRepository(BaseRepository[QATestEvidence]):
    """Tenant-scoped repository for QA test evidence files."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        super().__init__(QATestEvidence, db, org_id=org_id)

    async def list_for_bud(self, bud_id: uuid.UUID) -> list[QATestEvidence]:
        """List all evidence files for a BUD."""
        stmt = self._scoped(
            select(QATestEvidence)
            .where(QATestEvidence.bud_id == bud_id)
            .order_by(QATestEvidence.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_test_case(
        self, bud_id: uuid.UUID, test_case_id: str
    ) -> list[QATestEvidence]:
        """List all evidence files for a specific test case."""
        stmt = self._scoped(
            select(QATestEvidence)
            .where(
                QATestEvidence.bud_id == bud_id,
                QATestEvidence.test_case_id == test_case_id,
            )
            .order_by(QATestEvidence.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
