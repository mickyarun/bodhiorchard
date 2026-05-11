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

"""add dev_activity_logs table

Revision ID: 49c94f23fd15
Revises: 16f29f1b2a33
Create Date: 2026-03-26 11:32:26.478829

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "49c94f23fd15"
down_revision: str | None = "16f29f1b2a33"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dev_activity_logs",
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("bud_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("actor_name", sa.String(length=255), nullable=True),
        sa.Column("metadata_", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["bud_id"], ["bud_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dev_activity_bud_id", "dev_activity_logs", ["bud_id"], unique=False)
    op.create_index(
        "ix_dev_activity_org_created", "dev_activity_logs", ["org_id", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_dev_activity_org_created", table_name="dev_activity_logs")
    op.drop_index("ix_dev_activity_bud_id", table_name="dev_activity_logs")
    op.drop_table("dev_activity_logs")
