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

"""The remote JSON-RPC endpoint ``POST /mcp/sse`` on real rows.

Desktop AI clients use this route. It shares token auth and the audit log
with ``/mcp/tools/*`` but exposes only ``REMOTE_TOOLS`` and answers in
JSON-RPC envelopes.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import AsyncClient, Response

from app.mcp.streamable import _METHOD_NOT_FOUND
from tests.integration.mcp_seed import make_tenant, two_orgs
from tests.integration.mcp_support import (
    Factory,
    audit_rows,
    mcp_env,  # noqa: F401
    rpc,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("mcp_env")]


def _tool_result(response: Response) -> tuple[bool, dict[str, Any]]:
    """``(isError, decoded tool output)`` from a tools/call envelope."""
    result = response.json()["result"]
    return result["isError"], json.loads(result["content"][0]["text"])


async def test_valid_token_reads_own_org_and_is_audited_as_sse(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A remote call returns the org's BUDs and leaves an ``sse`` audit row."""
    org_a, _, _ = await two_orgs(pg_session_factory)

    response = await rpc(client, org_a.token, "get_bud_context", {"query": "BUD"})

    assert response.status_code == 200
    is_error, output = _tool_result(response)
    assert is_error is False
    assert [b["title"] for b in output["buds"]] == ["A's BUD"]
    (row,) = await audit_rows(pg_session_factory, org_a.org_id)
    assert (row.tool_name, row.transport, row.status_code) == ("get_bud_context", "sse", 200)
    assert (row.user_id, row.token_id, row.params) == (
        org_a.user_id,
        org_a.token_id,
        {"query": "BUD"},
    )


async def test_bad_token_is_401(client: AsyncClient, pg_session_factory: Factory) -> None:
    """The remote route refuses an unknown token before dispatch."""
    tenant = await make_tenant(pg_session_factory)

    response = await rpc(client, tenant.token + "x", "get_bud_context")

    assert response.status_code == 401
    assert await audit_rows(pg_session_factory, tenant.org_id) == []


async def test_other_org_bud_is_an_error_result(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """B's BUD id comes back as an isError result with no B content."""
    org_a, _, b_bud = await two_orgs(pg_session_factory)

    response = await rpc(client, org_a.token, "get_bud_by_id", {"bud_id": str(b_bud)})

    is_error, output = _tool_result(response)
    assert is_error is True
    assert output["code"] == "not_found"
    assert "B secret" not in response.text


async def test_internal_only_tool_is_not_found_and_audited(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """``write_bud`` exists on the HTTP tool route but not remotely."""
    tenant = await make_tenant(pg_session_factory)

    response = await rpc(
        client, tenant.token, "write_bud", {"title": "t", "requirements_md": "b", "bud_number": 1}
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == _METHOD_NOT_FOUND
    (row,) = await audit_rows(pg_session_factory, tenant.org_id)
    assert (row.tool_name, row.transport, row.status_code) == ("write_bud", "sse", 404)
