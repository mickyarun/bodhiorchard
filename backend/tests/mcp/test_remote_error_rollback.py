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

"""The remote endpoint's error path survives a rollback that fails too.

When a handler crashes, ``/mcp/sse`` rolls the session back before
answering. If that rollback raises (connection already gone), the call
must still be audited and still get its JSON-RPC error envelope.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.deps import get_db
from app.mcp import server as mcp_server
from app.mcp import streamable
from app.mcp.auth import MCPAuthResult, verify_mcp_token


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(streamable.router)
    app.dependency_overrides[verify_mcp_token] = lambda: MCPAuthResult(
        org=MagicMock(id=uuid.uuid4()), user=MagicMock(id=uuid.uuid4()), token_id=uuid.uuid4()
    )

    async def _db_with_broken_rollback() -> Any:
        yield MagicMock(rollback=AsyncMock(side_effect=ConnectionError("socket closed")))

    app.dependency_overrides[get_db] = _db_with_broken_rollback
    monkeypatch.setattr(streamable, "enforce_rate_limit", AsyncMock())
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_failed_rollback_still_audits_and_answers(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Crash plus failed rollback: one 500 audit row and the internal-error envelope."""
    audit_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(streamable, "emit_audit", lambda **kw: audit_calls.append(kw))

    async def _crash(db: Any, auth: Any, params: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("flush failed")

    monkeypatch.setitem(mcp_server.AUTH_TOOL_HANDLERS, "create_bud", _crash)

    response = client.post(
        "/mcp/sse",
        headers={"Authorization": "Bearer test"},
        json={
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "create_bud", "arguments": {"title": "t"}},
        },
    )

    assert response.status_code == 500
    assert response.json()["error"]["message"] == "Internal error"
    assert response.json()["id"] == 7
    assert [(c["tool_name"], c["status_code"]) for c in audit_calls] == [("create_bud", 500)]
