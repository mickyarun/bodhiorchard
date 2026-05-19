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

"""Append-only audit log for MCP tool calls.

Captures every MCP call (read + write, success + failure) so an org owner
can investigate a leaked token or anomalous activity. Rows are written
fire-and-forget from a background asyncio task so audit writes never
delay the user-facing tool response.

Retention is bounded by a periodic cleanup job
(``app.services.jobs.mcp_audit_cleanup``) that deletes rows older than
the configured window — 90 days by default.
"""

import uuid

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class MCPAuditLogEntry(BaseModel):
    """One row per MCP tool invocation.

    ``token_id`` is nullable because internal scan-pipeline tokens and
    legacy org-level token hashes have no ``user_mcp_tokens`` row to
    point at. ``user_id`` is nullable for the same reason.
    """

    __tablename__ = "mcp_audit_log"
    __table_args__ = (
        Index("ix_mcp_audit_org_created", "org_id", "created_at"),
        Index("ix_mcp_audit_token_created", "token_id", "created_at"),
        Index("ix_mcp_audit_created", "created_at"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    token_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_mcp_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    transport: Mapped[str] = mapped_column(String(16), nullable=False, default="http")
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # HTTP-style status: 200 success, 401 auth fail, 403 scope fail, 404
    # unknown tool, 429 rate-limited, 500 handler exception.
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
