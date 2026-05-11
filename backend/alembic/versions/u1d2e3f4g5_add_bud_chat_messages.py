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

"""Add bud_chat_messages table for persisted chat history.

Revision ID: u1d2e3f4g5
Revises: t0c1d2e3f4
Create Date: 2026-03-21 12:00:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "u1d2e3f4g5"
down_revision = "t0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bud_chat_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "bud_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bud_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section", sa.String(30), nullable=False),
        sa.Column(
            "design_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bud_designs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_bud_chat_bud_section",
        "bud_chat_messages",
        ["bud_id", "section"],
    )


def downgrade() -> None:
    op.drop_index("ix_bud_chat_bud_section", table_name="bud_chat_messages")
    op.drop_table("bud_chat_messages")
