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

"""Shared environment and HTTP helpers for the MCP integration tests.

Tests call ``/mcp/tools/{name}`` and ``/mcp/sse`` through the real router,
so token verification, dispatch and the handlers all run against Postgres.

The :func:`mcp_env` fixture points the audit writer and the token
``last_used_at`` toucher at the test database, turns rate limiting off (no
redis), replaces the embedding model with a fixed vector and empties the
internal token store, so no test reaches the developer's database, redis or
the ONNX model download. At teardown it waits for those fire-and-forget
writes, before the test database engine is disposed.

Test modules opt in with ``pytest.mark.usefixtures("mcp_env")`` after
importing the fixture.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.mcp import audit as mcp_audit
from app.mcp import auth as mcp_auth
from app.mcp import rate_limit as mcp_rate_limit
from app.models.mcp_audit_log import MCPAuditLogEntry
from app.services.embedding_service import embedding_service

Factory = async_sessionmaker[AsyncSession]

# bge-small dimension; any fixed unit vector keeps pgvector maths finite.
_EMBED_DIM = 384


async def _fixed_embedding(_text: str) -> list[float]:
    return [1.0] + [0.0] * (_EMBED_DIM - 1)


async def _no_redis() -> None:
    return None


async def drain_background() -> None:
    """Wait for fire-and-forget audit rows and last-used touches to land."""
    pending = [*mcp_audit._audit_tasks, *mcp_auth._last_used_tasks]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


@pytest_asyncio.fixture
async def mcp_env(
    monkeypatch: pytest.MonkeyPatch, pg_session_factory: Factory
) -> AsyncIterator[None]:
    """Keep MCP side channels inside the test and drain them at teardown.

    Depending on ``pg_session_factory`` makes this teardown run first, so
    no background write is still holding a connection when the engine goes.
    """
    monkeypatch.setattr(mcp_audit, "AsyncSessionLocal", pg_session_factory)
    monkeypatch.setattr(mcp_auth, "AsyncSessionLocal", pg_session_factory)
    monkeypatch.setattr(mcp_auth, "_internal_tokens", {})
    monkeypatch.setattr(mcp_rate_limit, "get_redis", _no_redis)
    monkeypatch.setattr(embedding_service, "embed", _fixed_embedding)
    yield
    await drain_background()


async def call(
    client: AsyncClient,
    token: str,
    tool: str,
    params: dict[str, Any] | None = None,
    **headers: str,
) -> Response:
    """POST one tool call over the HTTP tool route."""
    return await client.post(
        f"/mcp/tools/{tool}",
        json={"params": params or {}},
        headers={"Authorization": f"Bearer {token}", **headers},
    )


async def rpc(
    client: AsyncClient, token: str, tool: str, arguments: dict[str, Any] | None = None
) -> Response:
    """POST one JSON-RPC ``tools/call`` to the remote ``/mcp/sse`` endpoint."""
    return await client.post(
        "/mcp/sse",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments or {}},
        },
        headers={"Authorization": f"Bearer {token}"},
    )


async def audit_rows(factory: Factory, org_id: uuid.UUID) -> list[MCPAuditLogEntry]:
    """Every audit row for ``org_id``, oldest first."""
    await drain_background()
    async with factory() as db:
        rows = await db.scalars(
            select(MCPAuditLogEntry)
            .where(MCPAuditLogEntry.org_id == org_id)
            .order_by(MCPAuditLogEntry.created_at, MCPAuditLogEntry.id)
        )
        return list(rows)
