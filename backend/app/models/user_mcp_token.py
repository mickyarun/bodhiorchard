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
