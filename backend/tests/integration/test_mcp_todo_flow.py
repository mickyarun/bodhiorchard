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

"""Claiming and completing TODOs through the MCP tools, on real rows.

``takeover_todo`` is the only way to see a TODO's implementation notes and
must hand each TODO to exactly one developer, even when two claim it at
the same moment.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from tests.integration.mcp_seed import (
    add_member,
    dev_bud_with_todo,
    get_todo,
    make_tenant,
    mint_token,
)
from tests.integration.mcp_support import (
    Factory,
    call,
    mcp_env,  # noqa: F401
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("mcp_env")]


async def test_plan_hides_context_until_takeover(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """The plan lists titles only; a claim returns the notes and assigns the caller."""
    tenant = await make_tenant(pg_session_factory)
    bud_id = await dev_bud_with_todo(pg_session_factory, tenant)

    plan = await call(client, tenant.token, "get_bud_plan", {"bud_number": 3})
    claim = await call(client, tenant.token, "takeover_todo", {"bud_number": 3, "sequence": 1})

    assert "use the outbox table" not in plan.text
    assert claim.json()["todo"]["context_md"] == "use the outbox table"
    todo = await get_todo(pg_session_factory, bud_id, 1)
    assert (todo.status, todo.assignee_id) == ("in_progress", tenant.user_id)


async def test_second_claim_is_refused_and_keeps_the_first_holder(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A teammate can't take a TODO someone already holds."""
    tenant = await make_tenant(pg_session_factory)
    bud_id = await dev_bud_with_todo(pg_session_factory, tenant)
    peer = await add_member(pg_session_factory, tenant.org_id, "Peer")
    peer_token, _ = await mint_token(pg_session_factory, tenant.org_id, peer)

    await call(client, tenant.token, "takeover_todo", {"bud_number": 3, "sequence": 1})
    second = await call(client, peer_token, "takeover_todo", {"bud_number": 3, "sequence": 1})

    assert second.json()["success"] is False
    assert "already in_progress" in second.json()["error"]
    assert "use the outbox table" not in second.text
    assert (await get_todo(pg_session_factory, bud_id, 1)).assignee_id == tenant.user_id


async def test_simultaneous_claims_have_one_winner(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Two developers claiming at once: exactly one gets the TODO."""
    tenant = await make_tenant(pg_session_factory)
    bud_id = await dev_bud_with_todo(pg_session_factory, tenant)
    peer = await add_member(pg_session_factory, tenant.org_id, "Peer")
    peer_token, _ = await mint_token(pg_session_factory, tenant.org_id, peer)

    results = await asyncio.gather(
        call(client, tenant.token, "takeover_todo", {"bud_number": 3, "sequence": 1}),
        call(client, peer_token, "takeover_todo", {"bud_number": 3, "sequence": 1}),
    )

    winners = [r for r in results if r.json()["success"]]
    assert len(winners) == 1
    holder = (await get_todo(pg_session_factory, bud_id, 1)).assignee_id
    assert holder in (tenant.user_id, peer)


async def test_only_the_holder_completes_and_only_once(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Completing needs the claim; a second completion is refused."""
    tenant = await make_tenant(pg_session_factory)
    bud_id = await dev_bud_with_todo(pg_session_factory, tenant)
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
    todo = await get_todo(pg_session_factory, bud_id, 1)
    assert (todo.status, todo.summary) == ("completed", "wired the outbox")
