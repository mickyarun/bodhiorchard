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

Both orgs are given a BUD with the same number, so a lookup that forgot
its ``org_id`` filter would find the other org's row instead of failing.
Every write test re-reads the other org's row afterwards to prove it is
unchanged.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.bud import BUDDocument, BUDStatus
from app.models.bud_todo import BUDTodo
from tests.integration.mcp_support import (
    Factory,
    Tenant,
    add_bud,
    add_todo,
    call,
    isolate_side_channels,
    make_tenant,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _side_channels(monkeypatch: pytest.MonkeyPatch, pg_session_factory: Factory) -> None:
    isolate_side_channels(monkeypatch, pg_session_factory)


async def _two_orgs(factory: Factory) -> tuple[Tenant, Tenant, uuid.UUID]:
    """Org A and org B, each with BUD-001; returns B's BUD id."""
    org_a = await make_tenant(factory)
    org_b = await make_tenant(factory)
    await add_bud(factory, org_a.org_id, 1, title="A's BUD", assignee_id=org_a.user_id)
    b_bud = await add_bud(
        factory,
        org_b.org_id,
        1,
        title="B's BUD",
        requirements_md="B secret",
        assignee_id=org_b.user_id,
    )
    return org_a, org_b, b_bud


async def _bud(factory: Factory, bud_id: uuid.UUID) -> BUDDocument:
    async with factory() as db:
        bud = await db.get(BUDDocument, bud_id)
        assert bud is not None
        return bud


async def test_context_lists_only_own_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Listing and keyword search never surface the other org's BUDs."""
    org_a, _, _ = await _two_orgs(pg_session_factory)

    listed = await call(client, org_a.token, "get_bud_context", {"include_terminal": True})
    searched = await call(client, org_a.token, "get_bud_context", {"query": "secret"})

    assert [b["title"] for b in listed.json()["buds"]] == ["A's BUD"]
    assert searched.json()["buds"] == []


async def test_get_bud_by_id_refuses_other_org_uuid(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """B's UUID reads as not found for A; A's own number resolves A's BUD."""
    org_a, _, b_bud = await _two_orgs(pg_session_factory)

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
    org_a, _, b_bud = await _two_orgs(pg_session_factory)

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


async def test_write_bud_by_number_only_updates_own_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """``write_bud`` with a shared number edits A's BUD-001, never B's."""
    org_a, _, b_bud = await _two_orgs(pg_session_factory)

    response = await call(
        client,
        org_a.token,
        "write_bud",
        {"bud_number": 1, "title": "A renamed", "requirements_md": "A body"},
    )

    assert response.json()["updated"] is True
    after_b = await _bud(pg_session_factory, b_bud)
    assert (after_b.title, after_b.requirements_md) == ("B's BUD", "B secret")
    assert (await _bud(pg_session_factory, uuid.UUID(response.json()["id"]))).title == "A renamed"


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


async def test_plan_and_todo_tools_resolve_numbers_in_own_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A's BUD-001 plan never shows B's TODOs or their context."""
    org_a, org_b, b_bud = await _two_orgs(pg_session_factory)
    await add_todo(pg_session_factory, org_b.org_id, b_bud, 1, title="B step")

    plan = await call(client, org_a.token, "get_bud_plan", {"bud_number": 1})
    takeover = await call(client, org_a.token, "takeover_todo", {"bud_number": 1, "sequence": 1})

    assert plan.json()["todos"] == []
    assert takeover.json() == {"success": False, "error": "TODO #1 not found"}
    todo = await _only_todo(pg_session_factory, b_bud)
    assert (todo.assignee_id, todo.status) == (None, "pending")


async def _only_todo(factory: Factory, bud_id: uuid.UUID) -> BUDTodo:
    async with factory() as db:
        return (await db.scalars(select(BUDTodo).where(BUDTodo.bud_id == bud_id))).one()


async def test_todo_writes_never_land_on_other_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """create/update/complete against a number only B has are refused."""
    org_a = await make_tenant(pg_session_factory)
    org_b = await make_tenant(pg_session_factory)
    b_bud = await add_bud(pg_session_factory, org_b.org_id, 9, status=BUDStatus.DEVELOPMENT)
    await add_todo(
        pg_session_factory,
        org_b.org_id,
        b_bud,
        1,
        status="in_progress",
        assignee_id=org_b.user_id,
    )

    created = await call(client, org_a.token, "create_todo", {"bud_number": 9, "title": "x"})
    updated = await call(
        client, org_a.token, "update_todo", {"bud_number": 9, "sequence": 1, "title": "x"}
    )
    completed = await call(
        client, org_a.token, "complete_todo", {"bud_number": 9, "sequence": 1, "summary": "x"}
    )

    for response in (created, updated, completed):
        assert response.json() == {"success": False, "error": "BUD-009 not found"}
    todo = await _only_todo(pg_session_factory, b_bud)
    assert (todo.title, todo.status, todo.summary) == ("Step 1", "in_progress", None)


async def test_create_bud_drops_feature_ids_from_other_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Linking B's feature to A's new BUD is silently skipped, not stored."""
    org_a = await make_tenant(pg_session_factory)
    org_b = await make_tenant(pg_session_factory)
    seed = await call(
        client, org_b.token, "create_bud", {"title": "B feature", "requirements_md": "b"}
    )
    b_feature_id = await _planned_feature_id(client, org_b.token, seed.json()["bud_number"])

    response = await call(
        client,
        org_a.token,
        "create_bud",
        {"title": "A", "requirements_md": "a", "linked_feature_ids": [b_feature_id]},
    )

    assert response.json()["success"] is True
    assert response.json()["linked_features"] == {"linked_count": 0, "dropped": []}
    a_features = await call(client, org_a.token, "get_features", {"query": "Feature"})
    assert b_feature_id not in {f["id"] for f in a_features.json()["results"]}


async def _planned_feature_id(client: AsyncClient, token: str, bud_number: int) -> str:
    """The PLANNED feature row ``create_bud`` made for ``bud_number``."""
    response = await call(client, token, "get_features", {"query": "Feature"})
    ref = f"BUD-{bud_number:03d}"
    ids = [f["id"] for f in response.json()["results"] if f["source_ref"] == ref]
    assert len(ids) == 1, response.json()
    return str(ids[0])
