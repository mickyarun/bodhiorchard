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

"""History snapshots for the ``write_bud`` MCP update path.

An update through ``write_bud`` must leave exactly one ``bud_versions``
row holding the pre-edit content, so the History tab can restore what
the agent replaced. A write that changes nothing records no row.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.mcp import server as mcp_server
from app.mcp.auth import MCPAuthResult
from app.mcp.handlers_bud import handle_write_bud
from app.models.bud import BUDStatus
from app.models.bud_version import BUDEditSource
from app.repositories import bud_version as bud_version_repo
from app.repositories.bud import BUDRepository


def _bud(status: BUDStatus = BUDStatus.BUD) -> MagicMock:
    return MagicMock(
        id=uuid.uuid4(),
        bud_number=1,
        title="Demo",
        status=status,
        requirements_md="user-written description",
    )


def test_write_bud_is_dispatched_with_caller_identity() -> None:
    """The handler needs ``MCPAuthResult`` to attribute the snapshot."""
    assert mcp_server.AUTH_TOOL_HANDLERS["write_bud"] is handle_write_bud
    assert "write_bud" not in mcp_server.TOOL_HANDLERS


def _patch_lookup(monkeypatch: Any, bud: MagicMock) -> AsyncMock:
    async def _get(self: Any, number: int) -> MagicMock:
        return bud

    monkeypatch.setattr(BUDRepository, "get_by_number", _get)
    commit = AsyncMock()
    monkeypatch.setattr(bud_version_repo, "commit_snapshot", commit)
    return commit


@pytest.mark.asyncio
async def test_write_bud_update_snapshots_pre_edit_content(monkeypatch: Any) -> None:
    bud = _bud()
    commit = _patch_lookup(monkeypatch, bud)
    user = MagicMock(id=uuid.uuid4())
    auth = MCPAuthResult(org=MagicMock(id=uuid.uuid4()), user=user, token_id=uuid.uuid4())

    result = await handle_write_bud(
        MagicMock(),
        auth,
        {"bud_number": 1, "title": "Demo", "requirements_md": "agent rewrite"},
    )

    assert result["success"] is True
    commit.assert_awaited_once()
    kwargs = commit.await_args.kwargs
    assert kwargs["snapshot"]["requirements_md"] == "user-written description"
    assert kwargs["source"] == BUDEditSource.MCP
    assert kwargs["edited_by"] == user.id
    assert kwargs["mcp_token_id"] == auth.token_id
    assert kwargs["phase"] == BUDStatus.BUD
    assert bud.requirements_md == "agent rewrite"


@pytest.mark.asyncio
async def test_write_bud_update_without_user_token_still_snapshots(monkeypatch: Any) -> None:
    """Internal agent tokens carry no user; the row is still written, unattributed.

    The BUD has moved past ``bud`` status, but the snapshot is still filed
    under the Requirements phase so its history drawer shows it.
    """
    bud = _bud(status=BUDStatus.DESIGN)
    commit = _patch_lookup(monkeypatch, bud)
    auth = MCPAuthResult(org=MagicMock(id=uuid.uuid4()))

    await handle_write_bud(
        MagicMock(),
        auth,
        {"bud_number": 1, "title": "Renamed", "requirements_md": "user-written description"},
    )

    commit.assert_awaited_once()
    kwargs = commit.await_args.kwargs
    assert kwargs["snapshot"]["title"] == "Demo"
    assert kwargs["phase"] == BUDStatus.BUD
    assert kwargs["edited_by"] is None
    assert kwargs["mcp_token_id"] is None


@pytest.mark.asyncio
async def test_write_bud_unchanged_content_skips_snapshot(monkeypatch: Any) -> None:
    bud = _bud()
    commit = _patch_lookup(monkeypatch, bud)
    auth = MCPAuthResult(org=MagicMock(id=uuid.uuid4()))

    result = await handle_write_bud(
        MagicMock(),
        auth,
        {"bud_number": 1, "title": "Demo", "requirements_md": "user-written description"},
    )

    assert result["success"] is True
    commit.assert_not_awaited()
