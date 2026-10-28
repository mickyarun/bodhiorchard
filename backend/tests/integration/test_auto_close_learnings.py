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

"""An auto-closed BUD gets its learning metrics, like a manually closed one.

The closure hook reads ``bud.updated_at`` as the close time. After the
auto-close flips the status, that column is expired by the flush, and
lazy-loading it inside the async hook failed silently, so no
``FeatureLearning`` row was ever written for an auto-closed BUD.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bud import BUDDocument, BUDStatus
from app.models.feature_learning import FeatureLearning
from app.models.organization import Organization
from app.services.bud_timeline import record_event
from app.services.release_detection import _maybe_auto_close_bud

pytestmark = pytest.mark.integration


async def test_auto_close_records_learning_metrics(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A fully released prod BUD auto-closes and has a metrics envelope."""
    repo_id = str(uuid.uuid4())
    async with pg_session_factory() as db:
        org = Organization(name=f"AL {uuid.uuid4()}", slug=f"al-{uuid.uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        bud = BUDDocument(
            org_id=org.id,
            bud_number=1,
            title="t",
            status=BUDStatus.PROD,
            impacted_repos=[{"repo_id": repo_id, "repo_name": "api"}],
        )
        db.add(bud)
        await db.flush()
        await record_event(db, org.id, bud.id, "merged_to_prod", detail={"repo_id": repo_id})
        await db.commit()
        org_id, bud_id = org.id, bud.id

    no_model = AsyncMock(side_effect=RuntimeError("no model in tests"))
    async with pg_session_factory() as db:
        with patch("app.services.sp_attribution.run_agent_for_org_id", no_model):
            await _maybe_auto_close_bud(db, org_id, bud_id)
        await db.commit()

    async with pg_session_factory() as db:
        learning = await db.scalar(select(FeatureLearning).where(FeatureLearning.bud_id == bud_id))
        closed = await db.get(BUDDocument, bud_id)
    assert closed is not None and closed.status is BUDStatus.CLOSED
    assert learning is not None
    assert learning.metrics is not None
    assert "phase_metrics" in learning.metrics
