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

"""Organization model for multi-tenant isolation."""

from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, Index, Integer, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class AIProvider(StrEnum):
    """Which agent an organization runs its AI tasks through.

    Selected in setup / Settings → AI Config. ``claude`` is the default.
    ``claude``, ``copilot`` and ``codex`` each drive a CLI subprocess;
    ``ollama`` talks to a local HTTP server instead, for deployments where
    those CLIs cannot be installed. Stored as a Postgres enum.
    """

    claude = "claude"
    copilot = "copilot"
    codex = "codex"
    ollama = "ollama"


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
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
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
    # Which agent provider this org runs. The auth mode above and the
    # encrypted credential are reused per provider: the secret holds an
    # Anthropic key, a GitHub token, or an OpenAI key depending on
    # ``ai_provider``. Defaults to claude for backward-compat.
    ai_provider: Mapped[AIProvider] = mapped_column(
        SAEnum(AIProvider, name="ai_provider", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=AIProvider.claude.value,
    )
    # Base URL of the provider's HTTP server (Ollama only; the CLI providers
    # reach their backend themselves). NULL means "use the provider's default"
    # — resolved in code via ProviderCapabilities.default_base_url, so that
    # default can change without a migration.
    ai_base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Which model to run, for providers whose models live on the org's own host
    # rather than in our capability table. Skills name a model in their
    # frontmatter, but those are another provider's vocabulary ("sonnet",
    # "haiku") and mean nothing to a local server — so for those providers the
    # org chooses once, here, from what it actually has installed.
    ai_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Whether to let the model emit a reasoning trace before answering
    # (Ollama's `think`). Off by default: it roughly doubles latency for no
    # measurable gain on the short, structured tasks this provider handles,
    # and local inference is already the slowest link. Providers that express
    # reasoning as a level rather than a boolean use `effort` instead.
    ai_thinking: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, slug={self.slug!r})>"
