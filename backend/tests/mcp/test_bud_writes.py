# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Guard-rejection invariants for the BYO-AI write surface.

These pin the four behaviours that make the MCP write path safe from
prompt-injection scenarios:

1. ``update_bud`` rejects calls where the token's user isn't the BUD's
   assignee, even when the BUD belongs to the token's org.
2. ``update_bud`` rejects calls against terminal-status BUDs so a
   closed/discarded BUD can't be edited back to life via MCP.
3. ``update_bud`` rejects calls when the current phase has no editable
   field (e.g. DEVELOPMENT or UAT) — eliminates an entire class of
   "write the wrong field via MCP" injection.
4. ``create_bud`` requires a per-user token; org-level tokens are
   rejected so we never produce a BUD with no assignee-of-record.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.mcp.auth import MCPAuthResult
from app.mcp.handlers_bud_writes import (
    handle_create_bud,
    handle_get_bud_by_id,
    handle_update_bud,
)
from app.models.bud import BUDStatus
from app.repositories.bud import BUDRepository


def _auth(user_id: uuid.UUID | None = None) -> MCPAuthResult:
    org = MagicMock(id=uuid.uuid4())
    if user_id is None:
        return MCPAuthResult(org=org)
    user = MagicMock(id=user_id)
    return MCPAuthResult(org=org, user=user, token_id=uuid.uuid4())


def _fake_bud(
    *,
    status: BUDStatus = BUDStatus.BUD,
    assignee_id: uuid.UUID | None = None,
) -> MagicMock:
    return MagicMock(
        id=uuid.uuid4(),
        bud_number=42,
        title="Demo",
        status=status,
        assignee_id=assignee_id,
        requirements_md="body",
        tech_spec_md=None,
        test_plan_md=None,
        code_review_comments=None,
        auto_generate_phases=None,
    )


@pytest.mark.asyncio
async def test_update_bud_rejects_non_assignee(monkeypatch: Any) -> None:
    user_id = uuid.uuid4()
    other = uuid.uuid4()
    auth = _auth(user_id)
    bud = _fake_bud(assignee_id=other)

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)

    result = await handle_update_bud(
        MagicMock(), auth, {"bud_id": str(bud.id), "content": "new body"}
    )
    assert result["success"] is False
    assert result["code"] == "not_assignee"


@pytest.mark.asyncio
async def test_update_bud_rejects_terminal_status(monkeypatch: Any) -> None:
    user_id = uuid.uuid4()
    auth = _auth(user_id)
    bud = _fake_bud(status=BUDStatus.CLOSED, assignee_id=user_id)

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)

    result = await handle_update_bud(
        MagicMock(), auth, {"bud_id": str(bud.id), "content": "anything"}
    )
    assert result["success"] is False
    assert result["code"] == "terminal_status"


@pytest.mark.asyncio
async def test_update_bud_rejects_phase_with_no_owning_field(monkeypatch: Any) -> None:
    """DEVELOPMENT phase owns no markdown column — MCP cannot edit anything."""
    user_id = uuid.uuid4()
    auth = _auth(user_id)
    bud = _fake_bud(status=BUDStatus.DEVELOPMENT, assignee_id=user_id)

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)

    result = await handle_update_bud(
        MagicMock(), auth, {"bud_id": str(bud.id), "content": "anything"}
    )
    assert result["success"] is False
    assert result["code"] == "no_editable_field"
    assert result["current_status"] == "development"


@pytest.mark.asyncio
async def test_update_bud_writes_only_owning_field(monkeypatch: Any) -> None:
    """When the BUD is in TECH_ARCH, ``content`` lands in tech_spec_md —
    requirements_md must stay untouched even if the caller asks for it."""
    user_id = uuid.uuid4()
    auth = _auth(user_id)
    original_requirements = "original body"
    bud = _fake_bud(status=BUDStatus.TECH_ARCH, assignee_id=user_id)
    bud.requirements_md = original_requirements

    snapshots: list[dict[str, Any]] = []

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    async def _snapshot(db: Any, **kw: Any) -> Any:
        snapshots.append(kw)
        return MagicMock()

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)
    monkeypatch.setattr("app.mcp.handlers_bud_writes.bud_version_repo.insert_snapshot", _snapshot)

    db = MagicMock(flush=AsyncMock())

    result = await handle_update_bud(db, auth, {"bud_id": str(bud.id), "content": "NEW SPEC"})
    assert result["success"] is True
    assert result["field"] == "tech_spec_md"
    assert bud.tech_spec_md == "NEW SPEC"
    assert bud.requirements_md == original_requirements
    assert len(snapshots) == 1
    assert snapshots[0]["source"].value == "mcp"


@pytest.mark.asyncio
async def test_create_bud_requires_user_token() -> None:
    auth = _auth(user_id=None)
    result = await handle_create_bud(MagicMock(), auth, {"title": "T", "requirements_md": "B"})
    assert result["success"] is False
    assert result["code"] == "user_token_required"


@pytest.mark.asyncio
async def test_get_bud_by_id_org_scoped(monkeypatch: Any) -> None:
    """get_bud_by_id is read-only and works for any org member."""
    auth = _auth(uuid.uuid4())
    bud = _fake_bud()

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)

    result = await handle_get_bud_by_id(MagicMock(), auth, {"bud_id": str(bud.id)})
    assert result["bud_number"] == 42
    assert result["status"] == "bud"


@pytest.mark.asyncio
async def test_get_bud_by_id_rejects_bad_uuid() -> None:
    auth = _auth(uuid.uuid4())
    result = await handle_get_bud_by_id(MagicMock(), auth, {"bud_id": "not-a-uuid"})
    assert result["success"] is False
    assert result["code"] == "bad_bud_id"
