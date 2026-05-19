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

"""Per-user MCP tokens for authenticating Claude Code hook requests.

Each user in an organization can have multiple named MCP tokens, allowing
the backend to identify both the org and the specific developer from a
single Bearer token. Multiple tokens per (user, org) let a user issue
separate credentials to different machines / desktop AI clients with
different expiry windows and individually revocable scope.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

DEFAULT_TOKEN_NAME = "Default"


class UserMCPToken(BaseModel):
    """Per-user MCP token for Claude Code / external-AI authentication.

    Allows verify_mcp_token() to resolve both org and user from a single
    Bearer token. Multiple rows per (user, org) are permitted, distinguished
    by ``name`` — the legacy single-token endpoint maps to ``name='Default'``
    so existing Claude Code CLI installs keep working.

    The org-level Organization.mcp_token_hash is kept for backward
    compatibility — verify_mcp_token checks user tokens first, then
    falls back to the org token.
    """

    __tablename__ = "user_mcp_tokens"
    __table_args__ = (
        # Unique per (user, org, name) so a user can issue distinct named
        # tokens (e.g. "claude-desktop", "cursor-laptop") to different
        # machines and revoke them independently.
        Index("ix_user_mcp_token_user_org_name", "user_id", "org_id", "name", unique=True),
        Index("ix_user_mcp_token_prefix", "token_prefix"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    token_prefix: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="",
    )
    # Human-readable label so the user can tell their tokens apart in the
    # connect panel. Defaults to ``"Default"`` for backward compatibility
    # with the legacy single-token endpoint.
    name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=DEFAULT_TOKEN_NAME,
        server_default=DEFAULT_TOKEN_NAME,
    )
    # NULL = never expires (legacy / internal CLI tokens). All NEW tokens
    # minted via the multi-token endpoint MUST set this — enforced in the
    # handler, not at the DB layer, so internal flows that bypass the
    # handler still work.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set by verify_mcp_token via a fire-and-forget asyncio task on every
    # successful auth. Lets the user spot orphaned / unused tokens in the
    # connect panel and revoke them.
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", lazy="selectin")
    organization = relationship("Organization", lazy="selectin")

    def __repr__(self) -> str:
        return f"<UserMCPToken(user_id={self.user_id}, org_id={self.org_id}, name={self.name!r})>"
