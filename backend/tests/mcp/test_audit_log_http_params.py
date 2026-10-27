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

"""Successful calls on the HTTP tool route keep their params in the audit row.

Agent subprocesses reach the MCP server through the stdio bridge, which
posts to ``/mcp/tools/{name}``. That route recorded params on every failure
path but not on success, so a run of ``code_stats`` calls that all returned
an error envelope (HTTP 200) left ``mcp_audit_log.params`` NULL and no way
to see which ``repo_id`` the agent had sent.
"""

import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.deps import get_db
from app.mcp import server as mcp_server
from app.mcp.audit import _sanitise_params
from app.mcp.auth import MCPAuthResult, verify_mcp_token


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(mcp_server.router)
    app.dependency_overrides[verify_mcp_token] = lambda: MCPAuthResult(
        org=MagicMock(id=uuid.uuid4()), user=None, token_id=uuid.uuid4()
    )

    async def _fake_db() -> Any:
        yield MagicMock()

    app.dependency_overrides[get_db] = _fake_db
    monkeypatch.setattr(mcp_server, "enforce_rate_limit", AsyncMock())
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_success_audit_carries_params(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    audit_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(mcp_server, "emit_audit", lambda **kw: audit_calls.append(kw))

    async def _fake_stats(db: Any, org: Any, params: dict[str, Any]) -> dict[str, Any]:
        return {"error": "repo_id must be a tracked repository UUID"}

    monkeypatch.setitem(mcp_server.TOOL_HANDLERS, "code_stats", _fake_stats)

    response = client.post("/mcp/tools/code_stats", json={"params": {"repo_id": "taskflow-api"}})

    assert response.status_code == 200
    assert audit_calls[-1]["status_code"] == 200
    assert audit_calls[-1]["params"] == {"repo_id": "taskflow-api"}


def test_code_graph_arguments_survive_sanitisation() -> None:
    params = {
        "repo_id": "r",
        "symbol": "createTask",
        "target": "TaskService",
        "direction": "upstream",
        "depth": 2,
        "cluster_id": "c0",
        "api_key": "should-not-be-kept",
    }
    cleaned = _sanitise_params(params)
    assert cleaned is not None
    assert "api_key" not in cleaned
    assert cleaned == {k: v for k, v in params.items() if k != "api_key"}
