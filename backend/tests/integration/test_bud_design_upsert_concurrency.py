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

"""Concurrency proof for :meth:`BUDDesignRepository.upsert`.

Earlier shape-only tests verified that the generated ``SELECT`` statement
includes ``FOR UPDATE``; this test proves the runtime *behaviour* of that
lock against a real Postgres. Two ``asyncio.Task`` writers, each in a
separate ``AsyncSession`` / transaction, race to upsert the same
``(bud_id, repo_id=NULL)`` row with different ``design_html`` values. The
test asserts:

1. Neither task raises (the FOR UPDATE lock serializes them, the
   second waits for the first to commit).
2. The final ``design_html`` equals one of the two inputs verbatim —
   no torn writes / interleaving.
3. Exactly one ``bud_designs`` row exists for the ``(bud_id, NULL)``
   key (the second writer found the row inserted by the first and
   updated it instead of inserting a duplicate).

Gated by ``@pytest.mark.integration``; skipped by default. Run with
``pytest -m integration tests/integration/test_bud_design_upsert_concurrency.py``.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bud import BUDDesign, BUDDocument, BUDStatus
from app.models.organization import Organization
from app.repositories.bud import BUDDesignRepository

# Fixtures (``pg_container`` / ``pg_session_factory`` / ...) are
# auto-discovered from ``tests/integration/conftest.py`` — kept there
# rather than at the top-level so they never bleed into the default
# ``pytest`` run (which excludes the ``integration`` marker anyway).

pytestmark = pytest.mark.integration


async def _seed_org_and_bud(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert a minimal org + BUD row needed by the FK constraints."""
    async with factory() as db:
        org = Organization(name=f"Test Org {uuid.uuid4()}", slug=f"test-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        bud = BUDDocument(
            org_id=org.id,
            bud_number=1,
            title="Concurrency Test BUD",
            status=BUDStatus.DESIGN,
        )
        db.add(bud)
        await db.flush()
        await db.commit()
        return org.id, bud.id


async def _concurrent_upsert(
    factory: async_sessionmaker[AsyncSession],
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    html: str,
    barrier: asyncio.Event,
) -> None:
    """One half of the race: open a fresh session, await the barrier, upsert."""
    async with factory() as db:
        # All writers wait on the same barrier so both tasks reach the
        # repository call within a tight window — without this the
        # second writer could start AFTER the first has already
        # committed, defeating the race entirely.
        await barrier.wait()
        repo = BUDDesignRepository(db, org_id=org_id)
        await repo.upsert(bud_id, repo_id=None, design_html=html)
        await db.commit()


@pytest.mark.asyncio
async def test_concurrent_upsert_serializes_via_for_update(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two concurrent upserts on the same (bud, NULL) row commit cleanly.

    The final ``design_html`` is one of the two inputs verbatim (no
    torn write) and exactly one row exists.
    """
    factory = pg_session_factory
    org_id, bud_id = await _seed_org_and_bud(factory)

    barrier = asyncio.Event()
    task_a = asyncio.create_task(_concurrent_upsert(factory, org_id, bud_id, "A", barrier))
    task_b = asyncio.create_task(_concurrent_upsert(factory, org_id, bud_id, "B", barrier))
    # Let both tasks reach the barrier, then release them simultaneously.
    await asyncio.sleep(0.05)
    barrier.set()
    await asyncio.gather(task_a, task_b)

    async with factory() as db:
        result = await db.execute(
            select(BUDDesign).where(BUDDesign.bud_id == bud_id).where(BUDDesign.repo_id.is_(None))
        )
        rows = list(result.scalars().all())
        count_result = await db.execute(
            select(func.count())
            .select_from(BUDDesign)
            .where(BUDDesign.bud_id == bud_id)
            .where(BUDDesign.repo_id.is_(None))
        )
        row_count = count_result.scalar_one()

    assert row_count == 1, (
        f"Expected exactly one (bud, NULL) design row, found {row_count}. "
        "FOR UPDATE failed to prevent the duplicate-insert race."
    )
    assert len(rows) == 1
    final_html = rows[0].design_html
    assert final_html in ("A", "B"), (
        f"Final design_html={final_html!r} is neither input verbatim — "
        "concurrent writers tore the value."
    )
