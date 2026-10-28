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

"""Adding and editing TODOs through the MCP tools, and their param errors."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.bud import BUDStatus
from tests.integration.mcp_seed import (
    add_bud,
    dev_bud_with_todo,
    get_todo,
    make_tenant,
)
from tests.integration.mcp_support import (
    Factory,
    call,
    mcp_env,  # noqa: F401
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("mcp_env")]


async def test_create_and_update_todo(client: AsyncClient, pg_session_factory: Factory) -> None:
    """New TODOs append to the plan; edits change text, never status."""
    tenant = await make_tenant(pg_session_factory)
    bud_id = await dev_bud_with_todo(pg_session_factory, tenant)

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
    todo = await get_todo(pg_session_factory, bud_id, 2)
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
    await dev_bud_with_todo(pg_session_factory, tenant)

    response = await call(client, tenant.token, tool, params)

    assert response.status_code == 200
    assert response.json() == {"success": False, "error": error}
