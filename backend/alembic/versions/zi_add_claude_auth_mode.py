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

"""Add Claude Code auth mode columns to organizations.

Adds ``claude_auth_mode`` (default ``host``) and ``claude_api_key_encrypted``
so Full Docker deployments can store an encrypted per-org API key, while
Hybrid deployments keep the default ``host`` mode and continue to rely on
``ANTHROPIC_API_KEY`` from the backend process environment.

Revision ID: zi_claude_auth_mode
Revises: zh_race_results
Create Date: 2026-04-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zi_claude_auth_mode"
down_revision: str | None = "zh_race_results"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "claude_auth_mode",
            sa.String(length=20),
            nullable=False,
            server_default="host",
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("claude_api_key_encrypted", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "claude_api_key_encrypted")
    op.drop_column("organizations", "claude_auth_mode")
