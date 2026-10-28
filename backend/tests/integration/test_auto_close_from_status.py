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

"""The auto-close timeline event records the status the BUD closed from.

A BUD can be auto-closed straight from UAT; its ``status_change`` event
must say ``uat -> closed``, not a hard-coded ``prod -> closed``.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bud import BUDDocument, BUDStatus, BUDTimelineEvent
from app.models.organization import Organization
from app.services.bud_timeline import record_event
from app.services.release_detection import _maybe_auto_close_bud

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("status", [BUDStatus.UAT, BUDStatus.PROD])
async def test_auto_close_records_the_real_previous_status(
    pg_session_factory: async_sessionmaker[AsyncSession], status: BUDStatus
) -> None:
    """``from`` is the status the BUD was actually in."""
    repo_id = str(uuid.uuid4())
    async with pg_session_factory() as db:
        org = Organization(name=f"AC {uuid.uuid4()}", slug=f"ac-{uuid.uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        bud = BUDDocument(
            org_id=org.id,
            bud_number=1,
            title="t",
            status=status,
            impacted_repos=[{"repo_id": repo_id, "repo_name": "api"}],
        )
        db.add(bud)
        await db.flush()
        await record_event(db, org.id, bud.id, "merged_to_prod", detail={"repo_id": repo_id})
        await db.commit()
        org_id, bud_id = org.id, bud.id

    async with pg_session_factory() as db:
        with patch("app.services.bud_closure.on_bud_closed", AsyncMock()):
            await _maybe_auto_close_bud(db, org_id, bud_id)
        await db.commit()

    async with pg_session_factory() as db:
        details = list(
            await db.scalars(
                select(BUDTimelineEvent.detail).where(
                    BUDTimelineEvent.bud_id == bud_id,
                    BUDTimelineEvent.event_type == "status_change",
                )
            )
        )
    assert [(d["from"], d["to"]) for d in details] == [(status.value, "closed")]
