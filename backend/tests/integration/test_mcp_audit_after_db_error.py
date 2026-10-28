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

"""A tool call whose database write fails is still audited as a 500.

A failed flush rolls the request session back and expires every object
loaded in it, including the token's org and user. The error path read
``auth.org.id`` to write the audit row, which raised a second error, so
the failed call left no row and the client saw that second error.
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import hash_password
from app.mcp import audit, auth, rate_limit, server
from app.mcp.auth import MCPAuthResult, compute_token_prefix
from app.models.mcp_audit_log import MCPAuditLogEntry
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.models.user_mcp_token import UserMCPToken

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]


async def _no_redis() -> None:
    return None


async def _failing_write(db: AsyncSession, _auth: MCPAuthResult, _params: Any) -> dict[str, Any]:
    """A handler whose flush fails: the slug column is varchar(100)."""
    db.add(Organization(name="x", slug="s" * 200))
    await db.flush()
    return {"success": True}


@pytest.fixture
async def token(monkeypatch: pytest.MonkeyPatch, pg_session_factory: Factory) -> tuple[str, Any]:
    """A member token whose create_bud handler always fails on flush."""
    monkeypatch.setattr(audit, "AsyncSessionLocal", pg_session_factory)
    monkeypatch.setattr(auth, "AsyncSessionLocal", pg_session_factory)
    monkeypatch.setattr(rate_limit, "get_redis", _no_redis)
    monkeypatch.setitem(server.AUTH_TOOL_HANDLERS, "create_bud", _failing_write)
    plaintext = secrets.token_urlsafe(32)
    async with pg_session_factory() as db:
        org = Organization(name=f"Err {uuid.uuid4()}", slug=f"e-{uuid.uuid4().hex[:10]}")
        user = User(email=f"e-{uuid.uuid4().hex[:8]}@acme.dev", name="E", password_hash="x")
        db.add_all([org, user])
        await db.flush()
        db.add(OrgToUser(user_id=user.id, org_id=org.id))
        db.add(
            UserMCPToken(
                user_id=user.id,
                org_id=org.id,
                token_hash=hash_password(plaintext),
                token_prefix=compute_token_prefix(plaintext),
                name="t",
            )
        )
        await db.commit()
        return plaintext, org.id


async def _rows(factory: Factory, org_id: Any) -> list[tuple[str, str, int]]:
    await asyncio.gather(*audit._audit_tasks, *auth._last_used_tasks)
    async with factory() as db:
        rows = await db.scalars(select(MCPAuditLogEntry).where(MCPAuditLogEntry.org_id == org_id))
        return [(r.tool_name, r.transport, r.status_code) for r in rows]


async def test_http_route_audits_the_failed_write(
    client: AsyncClient, pg_session_factory: Factory, token: tuple[str, Any]
) -> None:
    """The original database error surfaces and a 500 row is stored."""
    plaintext, org_id = token

    with pytest.raises(DBAPIError):
        await client.post(
            "/mcp/tools/create_bud",
            json={"params": {"title": "t", "requirements_md": "b"}},
            headers={"Authorization": f"Bearer {plaintext}"},
        )

    assert await _rows(pg_session_factory, org_id) == [("create_bud", "http", 500)]


async def test_remote_route_answers_500_and_audits(
    client: AsyncClient, pg_session_factory: Factory, token: tuple[str, Any]
) -> None:
    """The JSON-RPC endpoint returns its internal-error envelope and a 500 row."""
    plaintext, org_id = token

    response = await client.post(
        "/mcp/sse",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "create_bud", "arguments": {"title": "t"}},
        },
        headers={"Authorization": f"Bearer {plaintext}"},
    )

    assert response.status_code == 500
    assert response.json()["error"]["message"] == "Internal error"
    assert await _rows(pg_session_factory, org_id) == [("create_bud", "sse", 500)]
