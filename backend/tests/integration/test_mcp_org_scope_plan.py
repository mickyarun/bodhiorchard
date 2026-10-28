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

"""Plan, TODO and feature-link tools stay inside the token's org.

BUD numbers are per org, so every lookup by number must resolve in the
caller's org; a number that only the other org has reads as not found.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.bud import BUDStatus
from app.models.bud_feature_link import BUDFeatureLink
from app.models.bud_todo import BUDTodo
from tests.integration.mcp_seed import add_bud, add_todo, make_tenant, two_orgs
from tests.integration.mcp_support import (
    Factory,
    call,
    mcp_env,  # noqa: F401
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("mcp_env")]


async def _only_todo(factory: Factory, bud_id: uuid.UUID) -> BUDTodo:
    async with factory() as db:
        return (await db.scalars(select(BUDTodo).where(BUDTodo.bud_id == bud_id))).one()


async def test_plan_and_takeover_resolve_numbers_in_own_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A's BUD-001 plan never shows B's TODOs, and B's TODO can't be claimed."""
    org_a, org_b, b_bud = await two_orgs(pg_session_factory)
    await add_todo(pg_session_factory, org_b.org_id, b_bud, 1, title="B step")

    plan = await call(client, org_a.token, "get_bud_plan", {"bud_number": 1})
    takeover = await call(client, org_a.token, "takeover_todo", {"bud_number": 1, "sequence": 1})

    assert plan.json()["todos"] == []
    assert takeover.json() == {"success": False, "error": "TODO #1 not found"}
    todo = await _only_todo(pg_session_factory, b_bud)
    assert (todo.assignee_id, todo.status) == (None, "pending")


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


async def test_create_bud_does_not_link_other_org_feature(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """B's feature id passed to A's create_bud creates no link row.

    Whether the skipped id should be reported back to the caller is an open
    question, so the response's ``dropped`` list is not asserted.
    """
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
    assert response.json()["linked_features"]["linked_count"] == 0
    async with pg_session_factory() as db:
        links = await db.scalars(
            select(BUDFeatureLink).where(BUDFeatureLink.feature_id == uuid.UUID(b_feature_id))
        )
        assert list(links) == []
    a_features = await call(client, org_a.token, "get_features", {"query": "Feature"})
    assert b_feature_id not in {f["id"] for f in a_features.json()["results"]}


async def _planned_feature_id(client: AsyncClient, token: str, bud_number: int) -> str:
    """The PLANNED feature row ``create_bud`` made for ``bud_number``."""
    response = await call(client, token, "get_features", {"query": "Feature"})
    ref = f"BUD-{bud_number:03d}"
    ids = [f["id"] for f in response.json()["results"] if f["source_ref"] == ref]
    assert len(ids) == 1, response.json()
    return str(ids[0])
