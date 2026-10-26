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

"""Section-session writes against real Postgres and their partial unique indexes.

``bud_section_sessions`` has two partial unique indexes, picked by whether
``design_id`` is NULL. Both writes covered here are ``INSERT ... ON
CONFLICT`` statements that must target the right one:

* ``upsert`` (a new CLI session id for a thread): a second writer racing
  the first's uncommitted row must wait on it and then update it, leaving
  one row with its own session id.
* ``try_claim_active_job``: a second claim on the same thread must hit the
  conflict and lose.

Both run for ordinary sections (``design_id`` NULL) and design threads.
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
from tests.integration.race_support import Write, race_against_uncommitted

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


@pytest.mark.asyncio
@pytest.mark.parametrize("on_design", [False, True], ids=["section", "design"])
async def test_racing_upserts_leave_one_row_with_the_second_session(
    pg_session_factory: async_sessionmaker[AsyncSession], on_design: bool
) -> None:
    """B waits on A's uncommitted thread row, then updates it: one row, B's session."""
    org_id, bud_id, design_id = await _seed(pg_session_factory)
    section = "design" if on_design else "requirements_md"
    target = design_id if on_design else None
    session_a, session_b = uuid.uuid4(), uuid.uuid4()

    def write(session_id: uuid.UUID) -> Write:
        return lambda db: BUDSectionSessionRepository(db, org_id=org_id).upsert(
            bud_id, section, session_id, design_id=target
        )

    b_blocked = await race_against_uncommitted(
        pg_session_factory, write(session_a), write(session_b)
    )

    async with pg_session_factory() as db:
        rows = (
            (await db.execute(select(BUDSectionSession).where(BUDSectionSession.bud_id == bud_id)))
            .scalars()
            .all()
        )

    assert b_blocked, "Second upsert did not wait for the first writer's uncommitted row."
    assert [(r.session_id, r.message_count) for r in rows] == [(session_b, 0)]
