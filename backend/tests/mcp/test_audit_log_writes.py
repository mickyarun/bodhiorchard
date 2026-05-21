# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""mcp_audit_log invariants for the BYO-AI write tools.

The remote POST handler is supposed to call ``emit_audit`` on every
code path — success, RPC error, dispatch crash, rate limit, JSON parse
failure. These tests pin that contract for the three new write-side
tools so a regression that drops the audit row would surface here, not
when an admin notices "I have no record of who edited BUD-42".
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport

from app.core.deps import get_db
from app.mcp import server as mcp_server
from app.mcp import streamable
from app.mcp.audit import _AUDITABLE_PARAM_KEYS
from app.mcp.auth import MCPAuthResult, verify_mcp_token


def _bypass_auth() -> MCPAuthResult:
    org = MagicMock(id=uuid.uuid4())
    user = MagicMock(id=uuid.uuid4())
    return MCPAuthResult(org=org, user=user, token_id=uuid.uuid4())


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Mounts only the streamable router with auth/rate-limit/db stubbed.

    We deliberately avoid spinning up the full app — these tests are
    about the audit contract, not the surrounding middleware.
    """
    app = FastAPI()
    app.include_router(streamable.router)
    app.dependency_overrides[verify_mcp_token] = _bypass_auth

    # Stub the request-scoped session — we never hit the DB in these tests.
    async def _fake_db() -> Any:
        yield MagicMock()

    app.dependency_overrides[get_db] = _fake_db
    # Rate limit is fail-open by design; stub it anyway so a missing
    # Redis in CI doesn't taint the audit-call assertions.
    monkeypatch.setattr(streamable, "enforce_rate_limit", AsyncMock())
    # ASGITransport raises_app_exceptions=False so we observe the JSON
    # response Body even when dispatch returns an error envelope.
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_auditable_param_keys_include_byoai_write_params() -> None:
    """The audit row sanitiser drops anything not in the allowlist; if
    a write-tool param isn't here, admin forensics on a leaked-token
    incident won't have the field to filter on."""
    for required in ("bud_id", "title", "content"):
        assert required in _AUDITABLE_PARAM_KEYS, (
            f"{required!r} missing — write-tool audit rows would not retain it"
        )


def test_create_bud_call_emits_audit_with_tool_name(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """A successful create_bud dispatch must call emit_audit with
    ``tool_name='create_bud'`` so admins can pivot the audit log by tool
    name."""
    audit_calls: list[dict[str, Any]] = []

    def _capture(**kw: Any) -> None:
        audit_calls.append(kw)

    monkeypatch.setattr(streamable, "emit_audit", _capture)

    # Stub the handler so we don't actually mutate the DB.
    async def _fake_create(db: Any, auth: Any, params: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "id": "fake", "bud_number": 1, "title": params["title"]}

    monkeypatch.setitem(mcp_server.AUTH_TOOL_HANDLERS, "create_bud", _fake_create)

    response = client.post(
        "/mcp/sse",
        headers={"Authorization": "Bearer test"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "create_bud",
                "arguments": {"title": "Hello", "requirements_md": "Body"},
            },
        },
    )

    assert response.status_code == 200
    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["tool_name"] == "create_bud"
    assert call["status_code"] == 200
    # Allowlisted params survive sanitisation; emit_audit receives the
    # raw dict and lets the audit layer filter — confirm we passed it.
    assert call["params"]["title"] == "Hello"


def test_dispatch_error_still_emits_audit(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Even when the handler crashes, the audit row must still be
    written so a flapping write can't escape forensic capture."""
    audit_calls: list[dict[str, Any]] = []

    def _capture(**kw: Any) -> None:
        audit_calls.append(kw)

    monkeypatch.setattr(streamable, "emit_audit", _capture)

    async def _crashing_handler(db: Any, auth: Any, params: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("boom")

    monkeypatch.setitem(mcp_server.AUTH_TOOL_HANDLERS, "update_bud", _crashing_handler)

    response = client.post(
        "/mcp/sse",
        headers={"Authorization": "Bearer test"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "update_bud",
                "arguments": {"bud_id": str(uuid.uuid4()), "content": "x"},
            },
        },
    )

    assert response.status_code == 500
    assert len(audit_calls) == 1
    assert audit_calls[0]["tool_name"] == "update_bud"
    assert audit_calls[0]["status_code"] == 500


def test_unknown_tool_emits_audit_with_404_status(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """A request for a tool not in REMOTE_TOOLS must still leave a
    forensic trail. Otherwise an attacker could probe handler names
    without ever appearing in the audit log."""
    audit_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        streamable,
        "emit_audit",
        lambda **kw: audit_calls.append(kw),  # noqa: ARG005
    )

    response = client.post(
        "/mcp/sse",
        headers={"Authorization": "Bearer test"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "delete_everything", "arguments": {}},
        },
    )

    assert response.status_code == 200  # JSON-RPC errors are 200 with error body
    body = json.loads(response.content)
    assert body["error"]["code"] == streamable._METHOD_NOT_FOUND
    assert audit_calls[-1]["tool_name"] == "delete_everything"
    assert audit_calls[-1]["status_code"] == 404


# Silence unused-import warnings for the ASGI transport we don't reference
# directly — TestClient picks it up via its constructor.
_ = ASGITransport
