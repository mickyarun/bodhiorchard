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

"""``mcp_audit_log`` rows as they land in Postgres.

The unit tests capture ``emit_audit`` calls; these check the stored row:
who called (org, user, token), from where, what status, and that only
allowlisted, size-capped params are kept.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.mcp.auth import create_internal_mcp_token
from tests.integration.mcp_support import (
    Factory,
    audit_rows,
    call,
    isolate_side_channels,
    make_tenant,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _side_channels(monkeypatch: pytest.MonkeyPatch, pg_session_factory: Factory) -> None:
    isolate_side_channels(monkeypatch, pg_session_factory)


async def test_success_row_names_caller_and_keeps_allowlisted_params(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A successful call records org, user, token, IP, user agent and safe params."""
    tenant = await make_tenant(pg_session_factory)

    response = await call(
        client,
        tenant.token,
        "get_bud_context",
        {"query": "tags", "limit": 3, "api_key": "sk-live-should-not-be-kept"},
        **{"User-Agent": "claude-desktop/1.0", "X-Forwarded-For": "203.0.113.9, 10.0.0.1"},
    )

    assert response.status_code == 200
    (row,) = await audit_rows(pg_session_factory, tenant.org_id)
    assert (row.tool_name, row.transport, row.status_code) == ("get_bud_context", "http", 200)
    assert (row.user_id, row.token_id) == (tenant.user_id, tenant.token_id)
    assert (row.ip, row.user_agent) == ("203.0.113.9", "claude-desktop/1.0")
    assert row.params == {"query": "tags", "limit": 3}


async def test_soft_error_result_is_still_a_200_row(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A handler refusal (error envelope) is audited with its params."""
    tenant = await make_tenant(pg_session_factory)

    response = await call(client, tenant.token, "get_bud_by_id", {"bud_number": 404})

    assert response.json()["code"] == "not_found"
    (row,) = await audit_rows(pg_session_factory, tenant.org_id)
    assert (row.tool_name, row.status_code, row.params) == (
        "get_bud_by_id",
        200,
        {"bud_number": 404},
    )


async def test_unknown_tool_leaves_a_404_row(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Probing for tool names is visible in the audit log."""
    tenant = await make_tenant(pg_session_factory)

    response = await call(client, tenant.token, "drop_all_tables", {"bud_id": "x"})

    assert response.status_code == 404
    (row,) = await audit_rows(pg_session_factory, tenant.org_id)
    assert (row.tool_name, row.status_code, row.params) == (
        "drop_all_tables",
        404,
        {"bud_id": "x"},
    )


async def test_long_param_values_are_capped(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A runaway content string is truncated to 500 chars plus an ellipsis."""
    tenant = await make_tenant(pg_session_factory)

    await call(client, tenant.token, "get_bud_context", {"query": "q" * 5000})

    (row,) = await audit_rows(pg_session_factory, tenant.org_id)
    assert row.params is not None
    assert row.params["query"] == "q" * 500 + "…"


async def test_internal_token_row_has_no_user_or_token(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Scan-pipeline calls are attributed to the org only."""
    tenant = await make_tenant(pg_session_factory)

    await call(client, create_internal_mcp_token(tenant.org_id), "get_team_context")

    (row,) = await audit_rows(pg_session_factory, tenant.org_id)
    assert (row.tool_name, row.user_id, row.token_id, row.params) == (
        "get_team_context",
        None,
        None,
        None,
    )


async def test_failed_auth_writes_no_row_for_any_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """An unauthenticated call can't be pinned to an org, so it isn't stored."""
    tenant = await make_tenant(pg_session_factory)

    response = await call(client, tenant.token + "x", "get_bud_context")

    assert response.status_code == 401
    assert await audit_rows(pg_session_factory, tenant.org_id) == []
