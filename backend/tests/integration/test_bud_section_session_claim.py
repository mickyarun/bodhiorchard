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

"""``try_claim_active_job`` against real Postgres and ``uq_bud_section_sessions_thread``.

The claim is an ``INSERT ... ON CONFLICT`` on a ``NULLS NOT DISTINCT``
constraint. A second claim on the same thread must hit the conflict and
lose, for ordinary sections (``design_id`` NULL) as well as design rows. If
NULLs were treated as distinct, the second claim on an ordinary section
would insert a new row and win.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bud import BUDDesign, BUDDesignStatus, BUDDocument, BUDStatus
from app.models.bud_section_session import BUDSectionSession
from app.models.organization import Organization
from app.repositories.bud_section_session import BUDSectionSessionRepository

pytestmark = pytest.mark.integration


async def _seed(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Insert an org, a BUD and one design row; return their ids."""
    async with factory() as db:
        org = Organization(name=f"Test Org {uuid.uuid4()}", slug=f"test-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        bud = BUDDocument(org_id=org.id, bud_number=1, title="Claim BUD", status=BUDStatus.DESIGN)
        db.add(bud)
        await db.flush()
        design = BUDDesign(org_id=org.id, bud_id=bud.id, status=BUDDesignStatus.READY)
        db.add(design)
        await db.commit()
        return org.id, bud.id, design.id


@pytest.mark.asyncio
@pytest.mark.parametrize("on_design", [False, True], ids=["section", "design"])
async def test_second_claim_on_a_thread_loses(
    pg_session_factory: async_sessionmaker[AsyncSession], on_design: bool
) -> None:
    """First claim creates the row and wins; a second claim on it loses."""
    org_id, bud_id, design_id = await _seed(pg_session_factory)
    section = "design" if on_design else "requirements_md"
    target = design_id if on_design else None

    async with pg_session_factory() as db:
        repo = BUDSectionSessionRepository(db, org_id=org_id)
        first = await repo.try_claim_active_job(bud_id, section, target, "job-1")
        await db.commit()
        second = await repo.try_claim_active_job(bud_id, section, target, "job-2")
        await db.commit()
        rows = (
            await db.execute(
                select(func.count())
                .select_from(BUDSectionSession)
                .where(BUDSectionSession.bud_id == bud_id)
            )
        ).scalar_one()

    assert first.won and first.session_id is not None
    assert not second.won
    assert rows == 1
