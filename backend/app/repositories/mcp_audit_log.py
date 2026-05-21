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

"""MCPAuditLogEntry data access."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mcp_audit_log import MCPAuditLogEntry
from app.repositories.base import BaseRepository


class MCPAuditLogRepository(BaseRepository[MCPAuditLogEntry]):
    """Append-only writer + retention cleanup for the MCP audit log."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(MCPAuditLogEntry, db)

    async def record(
        self,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID | None,
        token_id: uuid.UUID | None,
        tool_name: str,
        transport: str,
        ip: str | None,
        user_agent: str | None,
        status_code: int,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Insert one audit row. Caller commits."""
        self._db.add(
            MCPAuditLogEntry(
                org_id=org_id,
                user_id=user_id,
                token_id=token_id,
                tool_name=tool_name,
                transport=transport,
                ip=ip,
                user_agent=user_agent,
                status_code=status_code,
                params=params or None,
            )
        )

    async def delete_older_than(self, cutoff: datetime) -> int:
        """Retention cleanup. Returns rows deleted."""
        result = await self._db.execute(
            delete(MCPAuditLogEntry).where(MCPAuditLogEntry.created_at < cutoff)
        )
        return int(getattr(result, "rowcount", 0) or 0)
