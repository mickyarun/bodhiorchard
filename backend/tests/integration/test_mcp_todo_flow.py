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

"""The TODO plan tools on real rows: claim, complete, add and edit.

``takeover_todo`` is the only way to see a TODO's implementation notes and
must hand each TODO to exactly one developer, even when two claim it at
the same moment.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.bud import BUDStatus
from app.models.bud_todo import BUDTodo
from tests.integration.mcp_support import (
    Factory,
    Tenant,
    add_bud,
    add_member,
    add_todo,
    call,
    isolate_side_channels,
    make_tenant,
    mint_token,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _side_channels(monkeypatch: pytest.MonkeyPatch, pg_session_factory: Factory) -> None:
    isolate_side_channels(monkeypatch, pg_session_factory)


async def _todo(factory: Factory, bud_id: uuid.UUID, sequence: int) -> BUDTodo:
    async with factory() as db:
        row = await db.scalar(
            select(BUDTodo).where(BUDTodo.bud_id == bud_id, BUDTodo.sequence == sequence)
        )
        assert row is not None
        return row


async def _dev_bud(factory: Factory, tenant: Tenant) -> uuid.UUID:
    bud_id = await add_bud(factory, tenant.org_id, 3, status=BUDStatus.DEVELOPMENT)
    await add_todo(factory, tenant.org_id, bud_id, 1, context_md="use the outbox table")
    return bud_id


async def test_plan_hides_context_until_takeover(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """The plan lists titles only; a claim returns the notes and assigns the caller."""
    tenant = await make_tenant(pg_session_factory)
    bud_id = await _dev_bud(pg_session_factory, tenant)

    plan = await call(client, tenant.token, "get_bud_plan", {"bud_number": 3})
    claim = await call(client, tenant.token, "takeover_todo", {"bud_number": 3, "sequence": 1})

    assert "use the outbox table" not in plan.text
    assert claim.json()["todo"]["context_md"] == "use the outbox table"
    todo = await _todo(pg_session_factory, bud_id, 1)
    assert (todo.status, todo.assignee_id) == ("in_progress", tenant.user_id)


async def test_second_claim_is_refused_and_keeps_the_first_holder(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A teammate can't take a TODO someone already holds."""
    tenant = await make_tenant(pg_session_factory)
    bud_id = await _dev_bud(pg_session_factory, tenant)
    peer = await add_member(pg_session_factory, tenant.org_id, "Peer")
    peer_token, _ = await mint_token(pg_session_factory, tenant.org_id, peer)

    await call(client, tenant.token, "takeover_todo", {"bud_number": 3, "sequence": 1})
    second = await call(client, peer_token, "takeover_todo", {"bud_number": 3, "sequence": 1})

    assert second.json()["success"] is False
    assert "already in_progress" in second.json()["error"]
    assert "use the outbox table" not in second.text
    assert (await _todo(pg_session_factory, bud_id, 1)).assignee_id == tenant.user_id


async def test_simultaneous_claims_have_one_winner(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Two developers claiming at once: exactly one gets the TODO."""
    tenant = await make_tenant(pg_session_factory)
    bud_id = await _dev_bud(pg_session_factory, tenant)
    peer = await add_member(pg_session_factory, tenant.org_id, "Peer")
    peer_token, _ = await mint_token(pg_session_factory, tenant.org_id, peer)

    results = await asyncio.gather(
        call(client, tenant.token, "takeover_todo", {"bud_number": 3, "sequence": 1}),
        call(client, peer_token, "takeover_todo", {"bud_number": 3, "sequence": 1}),
    )

    winners = [r for r in results if r.json()["success"]]
    assert len(winners) == 1
    holder = (await _todo(pg_session_factory, bud_id, 1)).assignee_id
    assert holder in (tenant.user_id, peer)


async def test_only_the_holder_completes_and_only_once(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Completing needs the claim; a second completion is refused."""
    tenant = await make_tenant(pg_session_factory)
    bud_id = await _dev_bud(pg_session_factory, tenant)
    peer = await add_member(pg_session_factory, tenant.org_id, "Peer")
    peer_token, _ = await mint_token(pg_session_factory, tenant.org_id, peer)
    params = {"bud_number": 3, "sequence": 1, "summary": "  wired the outbox  "}

    unclaimed = await call(client, tenant.token, "complete_todo", params)
    await call(client, tenant.token, "takeover_todo", {"bud_number": 3, "sequence": 1})
    by_peer = await call(client, peer_token, "complete_todo", params)
    done = await call(client, tenant.token, "complete_todo", params)
    again = await call(client, tenant.token, "complete_todo", params)

    assert "not assigned to you" in unclaimed.json()["error"]
    assert "not assigned to you" in by_peer.json()["error"]
    assert done.json() == {"success": True, "remaining": 0}
    assert "is completed, not in_progress" in again.json()["error"]
    todo = await _todo(pg_session_factory, bud_id, 1)
    assert (todo.status, todo.summary) == ("completed", "wired the outbox")


async def test_create_and_update_todo(client: AsyncClient, pg_session_factory: Factory) -> None:
    """New TODOs append to the plan; edits change text, never status."""
    tenant = await make_tenant(pg_session_factory)
    bud_id = await _dev_bud(pg_session_factory, tenant)

    created = await call(
        client,
        tenant.token,
        "create_todo",
        {"bud_number": 3, "title": "  Add index  ", "description": "d" * 2000},
    )
    edited = await call(
        client, tenant.token, "update_todo", {"bud_number": 3, "sequence": 2, "title": "Index"}
    )
    empty = await call(client, tenant.token, "update_todo", {"bud_number": 3, "sequence": 2})
    missing = await call(
        client, tenant.token, "update_todo", {"bud_number": 3, "sequence": 9, "title": "x"}
    )

    assert created.json() == {"success": True, "sequence": 2, "title": "Add index"}
    assert edited.json() == {"success": True, "sequence": 2, "title": "Index"}
    assert empty.json()["error"] == "Provide title and/or description to update."
    assert missing.json()["error"] == "TODO #9 not found"
    todo = await _todo(pg_session_factory, bud_id, 2)
    assert (todo.title, todo.status, len(todo.description or "")) == ("Index", "pending", 1000)
    assert todo.detail == {"source": "manual"}


@pytest.mark.parametrize("status", [BUDStatus.CLOSED, BUDStatus.DISCARDED])
async def test_create_todo_refused_on_finished_bud(
    client: AsyncClient, pg_session_factory: Factory, status: BUDStatus
) -> None:
    """A closed or discarded plan can't grow."""
    tenant = await make_tenant(pg_session_factory)
    await add_bud(pg_session_factory, tenant.org_id, 4, status=status)

    response = await call(client, tenant.token, "create_todo", {"bud_number": 4, "title": "x"})

    assert response.json() == {
        "success": False,
        "error": f"Cannot add a TODO to a {status.value} BUD",
    }


@pytest.mark.parametrize(
    ("tool", "params", "error"),
    [
        ("takeover_todo", {"bud_number": 3}, "`sequence` is required"),
        ("complete_todo", {"bud_number": 3, "sequence": 1}, "`summary` is required"),
        (
            "complete_todo",
            {"bud_number": 3, "sequence": 1, "summary": "  "},
            "`summary` is required",
        ),
        ("create_todo", {"bud_number": 3}, "`title` is required"),
        ("update_todo", {"sequence": 1}, "`bud_number` is required"),
        ("get_bud_plan", {}, "bud_number is required"),
    ],
)
async def test_todo_tools_name_the_missing_param(
    client: AsyncClient,
    pg_session_factory: Factory,
    tool: str,
    params: dict[str, object],
    error: str,
) -> None:
    """Missing or blank required params come back as a readable error."""
    tenant = await make_tenant(pg_session_factory)
    await _dev_bud(pg_session_factory, tenant)

    response = await call(client, tenant.token, tool, params)

    assert response.status_code == 200
    assert response.json() == {"success": False, "error": error}
