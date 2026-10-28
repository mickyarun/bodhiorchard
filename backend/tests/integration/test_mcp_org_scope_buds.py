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

"""A token for one org can neither see nor change another org's BUDs.

Both orgs have a BUD-001 (see :func:`two_orgs`). Every write test re-reads
the other org's row afterwards to prove it is unchanged.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.bud import BUDDocument
from app.models.bud_version import BUDEditSource, BUDVersion
from tests.integration.mcp_seed import add_bud, make_tenant, two_orgs
from tests.integration.mcp_support import (
    Factory,
    call,
    mcp_env,  # noqa: F401
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("mcp_env")]


async def _bud(factory: Factory, bud_id: uuid.UUID) -> BUDDocument:
    async with factory() as db:
        bud = await db.get(BUDDocument, bud_id)
        assert bud is not None
        return bud


async def _versions(factory: Factory, bud_id: uuid.UUID) -> list[BUDVersion]:
    async with factory() as db:
        return list(await db.scalars(select(BUDVersion).where(BUDVersion.bud_id == bud_id)))


async def test_context_lists_only_own_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Listing and keyword search never surface the other org's BUDs."""
    org_a, _, _ = await two_orgs(pg_session_factory)

    listed = await call(client, org_a.token, "get_bud_context", {"include_terminal": True})
    searched = await call(client, org_a.token, "get_bud_context", {"query": "secret"})

    assert [b["title"] for b in listed.json()["buds"]] == ["A's BUD"]
    assert searched.json()["buds"] == []


async def test_get_bud_by_id_refuses_other_org_uuid(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """B's UUID reads as not found for A; A's own number resolves A's BUD."""
    org_a, _, b_bud = await two_orgs(pg_session_factory)

    by_uuid = await call(client, org_a.token, "get_bud_by_id", {"bud_id": str(b_bud)})
    by_number = await call(client, org_a.token, "get_bud_by_id", {"bud_number": 1})

    assert by_uuid.json()["code"] == "not_found"
    assert "B secret" not in by_uuid.text
    assert by_number.json()["title"] == "A's BUD"
    assert by_number.json()["is_assignee"] is True


async def test_update_bud_cannot_touch_other_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Content, title and priority writes against B's id all fail and change nothing."""
    org_a, _, b_bud = await two_orgs(pg_session_factory)

    response = await call(
        client,
        org_a.token,
        "update_bud",
        {
            "bud_id": str(b_bud),
            "content": "pwned",
            "expected_phase": "bud",
            "title": "pwned",
            "priority": "P0",
        },
    )

    assert response.json()["code"] == "not_found"
    after = await _bud(pg_session_factory, b_bud)
    assert (after.title, after.requirements_md, after.priority.value) == (
        "B's BUD",
        "B secret",
        "P2",
    )
    assert await _versions(pg_session_factory, b_bud) == []


async def test_write_bud_by_number_only_updates_own_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """``write_bud`` with a shared number edits A's BUD-001 and snapshots only A's."""
    org_a, _, b_bud = await two_orgs(pg_session_factory)

    response = await call(
        client,
        org_a.token,
        "write_bud",
        {"bud_number": 1, "title": "A renamed", "requirements_md": "A body"},
    )

    assert response.json()["updated"] is True
    a_bud = uuid.UUID(response.json()["id"])
    assert (await _bud(pg_session_factory, a_bud)).title == "A renamed"
    after_b = await _bud(pg_session_factory, b_bud)
    assert (after_b.title, after_b.requirements_md) == ("B's BUD", "B secret")
    (version,) = await _versions(pg_session_factory, a_bud)
    assert (version.source, version.edited_by) == (BUDEditSource.MCP, org_a.user_id)
    assert version.snapshot["title"] == "A's BUD"
    assert await _versions(pg_session_factory, b_bud) == []


async def test_write_bud_unknown_number_is_not_found(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A number that exists only in B is not found for A."""
    org_a = await make_tenant(pg_session_factory)
    org_b = await make_tenant(pg_session_factory)
    await add_bud(pg_session_factory, org_b.org_id, 7)

    response = await call(
        client, org_a.token, "write_bud", {"bud_number": 7, "title": "t", "requirements_md": "b"}
    )

    assert response.json() == {"success": False, "error": "BUD-007 not found"}
