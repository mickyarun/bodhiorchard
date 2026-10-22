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

Two writers in separate transactions upsert the same ``(bud_id, repo_id)``
key, forced into the worst interleaving instead of relying on timing:

1. Writer A upserts a BUD's first design and holds its transaction open,
   so its row exists but is uncommitted.
2. Writer B upserts the same key. It must block on A's row, which the
   test confirms by watching B's backend in ``pg_stat_activity``.
3. A commits; B then takes the update branch and commits.

The result must be exactly one row carrying B's value. A select-then-insert
upsert fails this every time: B sees no committed row, never blocks, and
inserts a duplicate (or, for a non-NULL repo, hits a unique violation).

Gated by ``@pytest.mark.integration``; skipped by default. Run with
``pytest -m integration tests/integration/test_bud_design_upsert_concurrency.py``.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bud import BUDDesign, BUDDesignStatus, BUDDocument, BUDStatus
from app.models.organization import Organization
from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.repositories.bud import BUDDesignRepository

# Fixtures (``pg_container`` / ``pg_session_factory`` / ...) are
# auto-discovered from ``tests/integration/conftest.py`` — kept there
# rather than at the top-level so they never bleed into the default
# ``pytest`` run (which excludes the ``integration`` marker anyway).

pytestmark = pytest.mark.integration

_BLOCK_TIMEOUT_S = 10.0


async def _seed(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Insert an org, a BUD and a tracked repo for the FK constraints."""
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
        repo = TrackedRepository(
            org_id=org.id, name="web", path="/data/repos/web", status=RepoStatus.ACTIVE
        )
        db.add_all([bud, repo])
        await db.flush()
        await db.commit()
        return org.id, bud.id, repo.id


async def _upsert_and_commit(
    factory: async_sessionmaker[AsyncSession],
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    repo_id: uuid.UUID | None,
    html: str,
    pid: asyncio.Future[int],
) -> None:
    """Writer B: publish its backend pid, then upsert and commit."""
    async with factory() as db:
        pid.set_result((await db.execute(text("SELECT pg_backend_pid()"))).scalar_one())
        await BUDDesignRepository(db, org_id=org_id).upsert(bud_id, repo_id, design_html=html)
        await db.commit()


async def _wait_until_lock_wait_or_done(
    factory: async_sessionmaker[AsyncSession], pid: int, task: asyncio.Task[None]
) -> None:
    """Return once backend ``pid`` is waiting on a lock, or ``task`` finished."""
    async with asyncio.timeout(_BLOCK_TIMEOUT_S), factory() as db:
        while not task.done():
            wait_type = (
                await db.execute(
                    text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                    {"pid": pid},
                )
            ).scalar_one_or_none()
            if wait_type == "Lock":
                return
            await asyncio.sleep(0.01)


async def _designs_for(
    factory: async_sessionmaker[AsyncSession], bud_id: uuid.UUID, repo_id: uuid.UUID | None
) -> list[BUDDesign]:
    """Fetch the committed design rows for one (bud_id, repo_id) key."""
    async with factory() as db:
        repo_match = (
            BUDDesign.repo_id.is_(None) if repo_id is None else BUDDesign.repo_id == repo_id
        )
        result = await db.execute(select(BUDDesign).where(BUDDesign.bud_id == bud_id, repo_match))
        return list(result.scalars().all())


@pytest.mark.asyncio
@pytest.mark.parametrize("repo_scoped", [False, True], ids=["bud_level", "repo_scoped"])
async def test_second_upsert_waits_for_first_and_updates_its_row(
    pg_session_factory: async_sessionmaker[AsyncSession], repo_scoped: bool
) -> None:
    """B blocks on A's uncommitted insert, then updates it: one row, B's value."""
    factory = pg_session_factory
    org_id, bud_id, tracked_repo_id = await _seed(factory)
    repo_id = tracked_repo_id if repo_scoped else None

    async with factory() as db_a:
        await BUDDesignRepository(db_a, org_id=org_id).upsert(bud_id, repo_id, design_html="A")

        pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        task_b = asyncio.create_task(
            _upsert_and_commit(factory, org_id, bud_id, repo_id, "B", pid)
        )
        b_pid = await asyncio.wait_for(pid, _BLOCK_TIMEOUT_S)
        await _wait_until_lock_wait_or_done(factory, b_pid, task_b)
        b_blocked = not task_b.done()
        await db_a.commit()

    await task_b
    rows = await _designs_for(factory, bud_id, repo_id)

    assert b_blocked, "Second upsert did not wait for the first writer's uncommitted row."
    assert len(rows) == 1, f"Expected exactly one design row for the key, found {len(rows)}."
    assert rows[0].design_html == "B"


@pytest.mark.asyncio
async def test_upsert_update_keeps_fields_not_passed(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A status-only upsert leaves html/notes/job_id as they were."""
    factory = pg_session_factory
    org_id, bud_id, _ = await _seed(factory)

    async with factory() as db:
        repo = BUDDesignRepository(db, org_id=org_id)
        first = await repo.upsert(bud_id, None, design_html="<p/>", notes="n", job_id="j1")
        created_at, first_updated_at = first.created_at, first.updated_at
        await db.commit()

    async with factory() as db:
        repo = BUDDesignRepository(db, org_id=org_id)
        second = await repo.upsert(bud_id, None, status=BUDDesignStatus.READY)
        await db.commit()

    assert second.id == first.id
    assert (second.design_html, second.notes, second.job_id) == ("<p/>", "n", "j1")
    assert second.status == BUDDesignStatus.READY
    assert second.created_at == created_at
    assert second.updated_at > first_updated_at

    async with factory() as db:
        count = (
            await db.execute(
                select(func.count()).select_from(BUDDesign).where(BUDDesign.bud_id == bud_id)
            )
        ).scalar_one()
    assert count == 1
