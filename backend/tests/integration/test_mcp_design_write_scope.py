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

"""``write_bud_design`` only writes onto the caller's own BUDs and repos.

A token for one org used to be able to create design rows (and a
``design_updated`` timeline event) on another org's BUD by passing that
BUD's UUID, with or without that org's repo id. The design repository now
refuses those targets itself, and an update that names another org's design
row by ``design_id`` is refused too.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.mcp.auth import MCPAuthResult
from app.mcp.handlers_bud_design import handle_write_bud_design
from app.models.bud import (
    BUDDesign,
    BUDDesignStatus,
    BUDDocument,
    BUDStatus,
    BUDTimelineEvent,
)
from app.models.organization import Organization
from app.models.tracked_repository import TrackedRepository

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]


async def _org_with_bud_and_repo(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with factory() as db:
        org = Organization(name=f"Design {uuid.uuid4()}", slug=f"d-{uuid.uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        bud = BUDDocument(org_id=org.id, bud_number=1, title="t", status=BUDStatus.DESIGN)
        repo = TrackedRepository(org_id=org.id, path=f"/tmp/{uuid.uuid4().hex}", name="web")
        db.add_all([bud, repo])
        await db.commit()
        return org.id, bud.id, repo.id


async def _write(factory: Factory, org_id: uuid.UUID, params: dict[str, str]) -> dict[str, object]:
    async with factory() as db:
        org = await db.get(Organization, org_id)
        assert org is not None
        return await handle_write_bud_design(db, MCPAuthResult(org=org), params)


async def _rows_on(factory: Factory, bud_id: uuid.UUID) -> tuple[int, int]:
    async with factory() as db:
        designs = (await db.scalars(select(BUDDesign).where(BUDDesign.bud_id == bud_id))).all()
        events = (
            await db.scalars(select(BUDTimelineEvent).where(BUDTimelineEvent.bud_id == bud_id))
        ).all()
        return len(designs), len(events)


@pytest.mark.parametrize("with_repo", [False, True])
async def test_other_org_bud_is_refused_and_untouched(
    pg_session_factory: Factory, with_repo: bool
) -> None:
    """Org A naming org B's BUD (and B's repo) writes nothing at all."""
    org_a, _, _ = await _org_with_bud_and_repo(pg_session_factory)
    _, b_bud, b_repo = await _org_with_bud_and_repo(pg_session_factory)
    params = {"bud_id": str(b_bud), "html": "<p>pwned</p>"}
    if with_repo:
        params["repo_id"] = str(b_repo)

    result = await _write(pg_session_factory, org_a, params)

    assert result == {
        "success": False,
        "error": f"No BUD with id {b_bud} in this organization",
    }
    assert await _rows_on(pg_session_factory, b_bud) == (0, 0)


async def test_other_org_repo_on_own_bud_is_refused(pg_session_factory: Factory) -> None:
    """A's own BUD with B's repo id is refused instead of linking B's repo."""
    org_a, a_bud, _ = await _org_with_bud_and_repo(pg_session_factory)
    _, _, b_repo = await _org_with_bud_and_repo(pg_session_factory)

    result = await _write(
        pg_session_factory,
        org_a,
        {"bud_id": str(a_bud), "repo_id": str(b_repo), "html": "<p>x</p>"},
    )

    assert result == {
        "success": False,
        "error": f"No tracked repository with id {b_repo} in this organization",
    }
    assert await _rows_on(pg_session_factory, a_bud) == (0, 0)


async def test_own_bud_and_repo_still_saves(pg_session_factory: Factory) -> None:
    """The normal agent write keeps working: one ready row and one event."""
    org_a, a_bud, a_repo = await _org_with_bud_and_repo(pg_session_factory)

    result = await _write(
        pg_session_factory,
        org_a,
        {"bud_id": str(a_bud), "repo_id": str(a_repo), "html": "<p>ok</p>"},
    )

    assert result["saved"] is True
    assert await _rows_on(pg_session_factory, a_bud) == (1, 1)


async def _seed_design(factory: Factory, org_id: uuid.UUID, bud_id: uuid.UUID) -> uuid.UUID:
    async with factory() as db:
        design = BUDDesign(
            org_id=org_id,
            bud_id=bud_id,
            design_html="<p>original</p>",
            status=BUDDesignStatus.READY,
        )
        db.add(design)
        await db.commit()
        return design.id


async def _design_html(factory: Factory, design_id: uuid.UUID) -> tuple[str | None, int]:
    """The row's HTML and the number of timeline events on its BUD."""
    async with factory() as db:
        design = await db.get(BUDDesign, design_id)
        assert design is not None
        _, events = await _rows_on(factory, design.bud_id)
        return design.design_html, events


async def test_other_org_design_id_is_refused_and_untouched(pg_session_factory: Factory) -> None:
    """Org A naming org B's design row (with B's BUD, or its own) changes nothing."""
    org_a, a_bud, _ = await _org_with_bud_and_repo(pg_session_factory)
    org_b, b_bud, _ = await _org_with_bud_and_repo(pg_session_factory)
    b_design = await _seed_design(pg_session_factory, org_b, b_bud)

    with_b_bud = await _write(
        pg_session_factory,
        org_a,
        {"bud_id": str(b_bud), "design_id": str(b_design), "html": "<p>pwned</p>"},
    )
    with_own_bud = await _write(
        pg_session_factory,
        org_a,
        {"bud_id": str(a_bud), "design_id": str(b_design), "html": "<p>pwned</p>"},
    )

    assert with_b_bud["success"] is False
    assert with_own_bud["success"] is False
    assert await _design_html(pg_session_factory, b_design) == ("<p>original</p>", 0)
    assert await _rows_on(pg_session_factory, a_bud) == (0, 0)


async def test_own_design_id_still_saves(pg_session_factory: Factory) -> None:
    """Chat iteration on the caller's own design row keeps working."""
    org_a, a_bud, _ = await _org_with_bud_and_repo(pg_session_factory)
    a_design = await _seed_design(pg_session_factory, org_a, a_bud)

    result = await _write(
        pg_session_factory,
        org_a,
        {"bud_id": str(a_bud), "design_id": str(a_design), "html": "<p>v2</p>"},
    )

    assert result["saved"] is True
    assert await _design_html(pg_session_factory, a_design) == ("<p>v2</p>", 1)
