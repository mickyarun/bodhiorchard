# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Organization model for multi-tenant isolation."""

from sqlalchemy import Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Organization(BaseModel):
    """Represents a tenant organization in the platform."""

    __tablename__ = "organizations"
    __table_args__ = (
        Index(
            "ix_org_mcp_token_hash",
            "mcp_token_hash",
            postgresql_where=text("mcp_token_hash IS NOT NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    github_app_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    github_app_private_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_app_installation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    github_webhook_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Lowercase App slug from `GET /app` (e.g. "my-org-bodhi"). Used to build
    # the install URL https://github.com/apps/{slug}/installations/new for
    # the bulk-import flow. Auto-populated on first successful App-token
    # use; never user-edited; not a secret so stored plain text.
    github_app_slug: Mapped[str | None] = mapped_column(String(120), nullable=True)
    slack_bot_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    slack_signing_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    slack_team_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    mcp_token_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Claude Code authentication:
    #   "host"    — inherit ANTHROPIC_API_KEY from the backend process env
    #               (Hybrid mode with host-installed claude, or Full Docker with
    #               a compose-level env var)
    #   "api_key" — inject the decrypted claude_api_key_encrypted at subprocess
    #               launch (Full Docker with a per-org key entered in Settings)
    claude_auth_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="host"
    )
    claude_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, slug={self.slug!r})>"
