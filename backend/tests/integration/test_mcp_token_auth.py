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

"""Who may call ``/mcp/tools/*``: every token shape against real rows.

The mocked unit tests in ``tests/mcp`` pin each branch of
``verify_mcp_token``; these run the whole route on Postgres so a broken
prefix index, a missing membership join or a role lookup that drifts
from the HTTP path shows up as a wrong status code.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, update

from app.mcp.auth import create_internal_mcp_token
from app.models.user import OrgToUser, User
from app.models.user_mcp_token import UserMCPToken
from tests.integration.leave_support import give_role
from tests.integration.mcp_seed import (
    add_bud,
    make_tenant,
    set_org_token,
)
from tests.integration.mcp_support import (
    Factory,
    call,
    drain_background,
    mcp_env,  # noqa: F401
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("mcp_env")]


async def test_valid_user_token_reads_own_org_and_records_last_use(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A live token returns its org's data and stamps ``last_used_at``."""
    tenant = await make_tenant(pg_session_factory)
    await add_bud(pg_session_factory, tenant.org_id, 1, title="Mine")

    response = await call(client, tenant.token, "get_bud_context")

    assert response.status_code == 200
    assert [b["title"] for b in response.json()["buds"]] == ["Mine"]
    await drain_background()
    async with pg_session_factory() as db:
        row = await db.get(UserMCPToken, tenant.token_id)
        assert row is not None and row.last_used_at is not None


async def test_missing_authorization_header_is_rejected(client: AsyncClient) -> None:
    """No header at all never reaches a handler."""
    response = await client.post("/mcp/tools/get_bud_context", json={"params": {}})
    assert response.status_code == 422


@pytest.mark.parametrize("header", ["Token abc", "bearer abc", "Bearer", ""])
async def test_malformed_authorization_header_is_401(client: AsyncClient, header: str) -> None:
    """Only ``Bearer <token>`` is accepted."""
    response = await client.post(
        "/mcp/tools/get_bud_context", json={"params": {}}, headers={"Authorization": header}
    )
    assert response.status_code == 401


async def test_unknown_token_is_401(client: AsyncClient) -> None:
    """A random string matches no token row and no org token."""
    response = await call(client, "not-a-real-token-" + "x" * 30, "get_bud_context")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired MCP token"


async def test_expired_token_is_401(client: AsyncClient, pg_session_factory: Factory) -> None:
    """A token past ``expires_at`` stops working even though the row exists."""
    tenant = await make_tenant(pg_session_factory, expires_at=datetime.now(UTC) - timedelta(1))
    response = await call(client, tenant.token, "get_bud_context")
    assert response.status_code == 401
    assert response.json()["detail"] == "Token has expired"


async def test_token_expiring_later_still_works(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """An expiry in the future is not treated as expired."""
    tenant = await make_tenant(pg_session_factory, expires_at=datetime.now(UTC) + timedelta(1))
    response = await call(client, tenant.token, "get_bud_context")
    assert response.status_code == 200


async def test_revoked_token_is_401(client: AsyncClient, pg_session_factory: Factory) -> None:
    """Deleting the row (revoke in settings) cuts the token off at once."""
    tenant = await make_tenant(pg_session_factory)
    assert (await call(client, tenant.token, "get_bud_context")).status_code == 200
    async with pg_session_factory() as db:
        await db.execute(delete(UserMCPToken).where(UserMCPToken.id == tenant.token_id))
        await db.commit()

    response = await call(client, tenant.token, "get_bud_context")
    assert response.status_code == 401


async def test_deactivated_user_token_is_401(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A soft-deleted member's surviving token is refused."""
    tenant = await make_tenant(pg_session_factory)
    async with pg_session_factory() as db:
        await db.execute(update(User).where(User.id == tenant.user_id).values(is_active=False))
        await db.commit()

    response = await call(client, tenant.token, "get_bud_context")
    assert response.status_code == 401
    assert response.json()["detail"] == "Account is deactivated"


async def test_token_of_removed_member_is_401(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A token whose owner is no longer in the org can't read it."""
    tenant = await make_tenant(pg_session_factory)
    async with pg_session_factory() as db:
        await db.execute(delete(OrgToUser).where(OrgToUser.user_id == tenant.user_id))
        await db.commit()

    response = await call(client, tenant.token, "get_bud_context")
    assert response.status_code == 401


async def test_role_without_engineering_access_is_403(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Moving a member to a people-only role cuts their existing token off."""
    tenant = await make_tenant(pg_session_factory)
    await give_role(pg_session_factory, tenant.org_id, tenant.user_id, "hr")

    response = await call(client, tenant.token, "get_bud_context")
    assert response.status_code == 403


async def test_org_level_token_reads_but_cannot_write(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """The legacy org token authenticates, but user-attributed tools refuse it."""
    tenant = await make_tenant(pg_session_factory)
    await add_bud(pg_session_factory, tenant.org_id, 1, title="Org visible")
    org_token = await set_org_token(pg_session_factory, tenant.org_id)

    read = await call(client, org_token, "get_bud_context")
    create = await call(client, org_token, "create_bud", {"title": "x", "requirements_md": "y"})
    takeover = await call(client, org_token, "takeover_todo", {"bud_number": 1, "sequence": 1})

    assert read.status_code == 200
    assert [b["title"] for b in read.json()["buds"]] == ["Org visible"]
    assert (create.status_code, takeover.status_code) == (200, 200)
    assert create.json()["code"] == "user_token_required"
    assert takeover.json()["success"] is False
    assert "per-user" in takeover.json()["error"]


async def test_internal_token_is_bound_to_its_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A scan-pipeline token reads only the org it was minted for."""
    mine = await make_tenant(pg_session_factory)
    other = await make_tenant(pg_session_factory)
    await add_bud(pg_session_factory, mine.org_id, 1, title="Scan org")
    await add_bud(pg_session_factory, other.org_id, 1, title="Other org")

    response = await call(client, create_internal_mcp_token(mine.org_id), "get_bud_context")

    assert response.status_code == 200
    assert [b["title"] for b in response.json()["buds"]] == ["Scan org"]
