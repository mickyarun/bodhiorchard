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

"""An oversized tool name, IP or user agent still leaves an audit row.

All three are caller-controlled. Before the fix a value wider than its
column failed the insert, the failure was swallowed, and the call left
no trace: sending a long ``User-Agent`` was enough to hide from the log.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.mcp import audit
from app.mcp.auth import MCPAuthResult
from app.models.mcp_audit_log import MCPAuditLogEntry
from app.models.organization import Organization

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]


async def _org(factory: Factory) -> Organization:
    async with factory() as db:
        org = Organization(name=f"Audit {uuid.uuid4()}", slug=f"a-{uuid.uuid4().hex[:10]}")
        db.add(org)
        await db.commit()
        return org


def _request(headers: dict[str, str]) -> MagicMock:
    return MagicMock(headers=headers, client=MagicMock(host="127.0.0.1"))


@pytest.mark.parametrize(
    ("tool", "headers", "column", "width"),
    [
        ("get_bud_context", {"user-agent": "u" * 300}, "user_agent", 256),
        ("get_bud_context", {"x-forwarded-for": "9" * 80 + ", 10.0.0.1"}, "ip", 64),
        ("t" * 80, {}, "tool_name", 64),
    ],
)
async def test_oversized_value_is_cut_and_row_kept(
    monkeypatch: pytest.MonkeyPatch,
    pg_session_factory: Factory,
    tool: str,
    headers: dict[str, str],
    column: str,
    width: int,
) -> None:
    """The row lands, with the long value cut to the column width."""
    monkeypatch.setattr(audit, "AsyncSessionLocal", pg_session_factory)
    org = await _org(pg_session_factory)

    audit.emit_audit(
        request=_request(headers),
        auth=MCPAuthResult(org=org),
        org_id=org.id,
        token_id=None,
        tool_name=tool,
        transport="http",
        status_code=404,
    )
    await asyncio.gather(*audit._audit_tasks)

    async with pg_session_factory() as db:
        rows = (
            await db.scalars(select(MCPAuditLogEntry).where(MCPAuditLogEntry.org_id == org.id))
        ).all()
    assert len(rows) == 1
    stored = getattr(rows[0], column)
    assert len(stored) == width
    assert stored == {"user_agent": "u", "ip": "9", "tool_name": "t"}[column] * width
