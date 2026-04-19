# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

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
