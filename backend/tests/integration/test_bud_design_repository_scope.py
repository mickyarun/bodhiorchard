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

"""``BUDDesignRepository`` refuses design writes outside its own org.

``bud_designs.bud_id`` and ``bud_designs.repo_id`` are plain foreign keys, so
the repository is where the org scope is enforced for every caller (MCP
tools, the designs API, BUD revert). These run against real Postgres.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bud import BUDDesign, BUDDesignStatus, BUDDocument, BUDStatus
from app.models.organization import Organization
from app.models.tracked_repository import TrackedRepository
from app.repositories.bud import BUDDesignRepository, DesignTargetNotInOrgError

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]


async def _org_with_bud_and_repo(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with factory() as db:
        org = Organization(name=f"Scope {uuid.uuid4()}", slug=f"s-{uuid.uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        bud = BUDDocument(org_id=org.id, bud_number=1, title="t", status=BUDStatus.DESIGN)
        repo = TrackedRepository(org_id=org.id, path=f"/tmp/{uuid.uuid4().hex}", name="web")
        db.add_all([bud, repo])
        await db.commit()
        return org.id, bud.id, repo.id


async def _design_count(factory: Factory, bud_id: uuid.UUID) -> int:
    async with factory() as db:
        rows = (await db.scalars(select(BUDDesign).where(BUDDesign.bud_id == bud_id))).all()
        return len(rows)


async def test_upsert_refuses_another_orgs_bud(pg_session_factory: Factory) -> None:
    org_a, _, a_repo = await _org_with_bud_and_repo(pg_session_factory)
    _, b_bud, _ = await _org_with_bud_and_repo(pg_session_factory)

    async with pg_session_factory() as db:
        with pytest.raises(DesignTargetNotInOrgError) as excinfo:
            await BUDDesignRepository(db, org_id=org_a).upsert(b_bud, a_repo, design_html="x")
        await db.commit()

    assert excinfo.value.kind == "bud"
    assert await _design_count(pg_session_factory, b_bud) == 0


async def test_upsert_refuses_another_orgs_repo(pg_session_factory: Factory) -> None:
    org_a, a_bud, _ = await _org_with_bud_and_repo(pg_session_factory)
    _, _, b_repo = await _org_with_bud_and_repo(pg_session_factory)

    async with pg_session_factory() as db:
        with pytest.raises(DesignTargetNotInOrgError) as excinfo:
            await BUDDesignRepository(db, org_id=org_a).upsert(a_bud, b_repo, design_html="x")
        await db.commit()

    assert excinfo.value.kind == "repo"
    assert await _design_count(pg_session_factory, a_bud) == 0


async def test_upsert_writes_own_bud_and_repo(pg_session_factory: Factory) -> None:
    org_a, a_bud, a_repo = await _org_with_bud_and_repo(pg_session_factory)

    async with pg_session_factory() as db:
        await BUDDesignRepository(db, org_id=org_a).upsert(a_bud, a_repo, design_html="x")
        await BUDDesignRepository(db, org_id=org_a).upsert(a_bud, None, design_html="y")
        await db.commit()

    assert await _design_count(pg_session_factory, a_bud) == 2


async def test_write_ready_html_refuses_a_row_pointing_at_another_orgs_bud(
    pg_session_factory: Factory,
) -> None:
    """A row stamped with org A but pointing at B's BUD (written before the
    check existed) can't be used to keep writing onto B's BUD."""
    org_a, _, _ = await _org_with_bud_and_repo(pg_session_factory)
    _, b_bud, _ = await _org_with_bud_and_repo(pg_session_factory)
    async with pg_session_factory() as db:
        stray = BUDDesign(
            org_id=org_a, bud_id=b_bud, design_html="old", status=BUDDesignStatus.READY
        )
        db.add(stray)
        await db.commit()

    async with pg_session_factory() as db:
        with pytest.raises(DesignTargetNotInOrgError):
            await BUDDesignRepository(db, org_id=org_a).write_ready_html(
                stray.id, b_bud, design_html="new"
            )
        await db.commit()

    async with pg_session_factory() as db:
        reread = await db.get(BUDDesign, stray.id)
        assert reread is not None
        assert reread.design_html == "old"
