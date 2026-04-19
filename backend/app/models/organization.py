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
    slack_bot_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    slack_signing_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    slack_team_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    mcp_token_hash: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, slug={self.slug!r})>"
