# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Per-user MCP tokens for authenticating Claude Code hook requests.

Each user in an organization can have their own MCP token, allowing
the backend to identify both the org and the specific developer
from a single Bearer token.
"""

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class UserMCPToken(BaseModel):
    """Per-user MCP token for Claude Code authentication.

    Allows verify_mcp_token() to resolve both org and user from a
    single Bearer token, replacing the org-level-only approach.

    The org-level Organization.mcp_token_hash is kept for backward
    compatibility — verify_mcp_token checks user tokens first, then
    falls back to the org token.
    """

    __tablename__ = "user_mcp_tokens"
    __table_args__ = (
        Index("ix_user_mcp_token_user_org", "user_id", "org_id", unique=True),
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

    user = relationship("User", lazy="selectin")
    organization = relationship("Organization", lazy="selectin")

    def __repr__(self) -> str:
        return f"<UserMCPToken(user_id={self.user_id}, org_id={self.org_id})>"
