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

"""Add bud_todos table for TODO splitting + multi-developer assignment.

Creates the ``bud_todos`` table that stores discrete work items parsed
from each BUD's tech spec.  Each TODO tracks its own assignee, status,
and implementation context — enabling parallel work across developers
within a single BUD phase.

Also cleans up incidental schema drift surfaced by autogenerate:
  - Adds missing ``ix_bugs_bud_id_status`` index (declared in model)
  - Sets NOT NULL on ``jira_import_sessions`` and
    ``jira_issue_bud_map`` timestamps (BaseModel inherits NOT NULL
    from TimestampMixin but prior migration missed it)

Revision ID: d9c7f018e768
Revises: zf_jira_import
Create Date: 2026-04-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d9c7f018e768"
down_revision: str | None = "zf_jira_import"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── bud_todos table ────────────────────────────────────────
    op.create_table(
        "bud_todos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "bud_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bud_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("phase", sa.String(length=30), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "is_checkpoint",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "assignee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("context_md", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("bud_id", "sequence", name="uq_bud_todo_seq"),
    )
    op.create_index("ix_bud_todo_bud", "bud_todos", ["bud_id"])
    op.create_index("ix_bud_todo_assignee", "bud_todos", ["assignee_id"])
    op.create_index("ix_bud_todo_org_status", "bud_todos", ["org_id", "status"])

    # ── Incidental drift fixes ────────────────────────────────
    # Use IF NOT EXISTS: zd_bug_type_column already creates this index,
    # so fresh schemas already have it by the time this migration runs.
    op.execute("CREATE INDEX IF NOT EXISTS ix_bugs_bud_id_status ON bugs (bud_id, status)")

    for table in ("jira_import_sessions", "jira_issue_bud_map"):
        for col in ("created_at", "updated_at"):
            op.alter_column(
                table,
                col,
                existing_type=postgresql.TIMESTAMP(timezone=True),
                nullable=False,
                existing_server_default=sa.text("now()"),
            )


def downgrade() -> None:
    # Revert drift fixes
    for table in ("jira_issue_bud_map", "jira_import_sessions"):
        for col in ("updated_at", "created_at"):
            op.alter_column(
                table,
                col,
                existing_type=postgresql.TIMESTAMP(timezone=True),
                nullable=True,
                existing_server_default=sa.text("now()"),
            )
    # Mirror the guarded upgrade: zd_bug_type_column's downgrade drops it.
    op.execute("DROP INDEX IF EXISTS ix_bugs_bud_id_status")

    # Drop bud_todos
    op.drop_index("ix_bud_todo_org_status", table_name="bud_todos")
    op.drop_index("ix_bud_todo_assignee", table_name="bud_todos")
    op.drop_index("ix_bud_todo_bud", table_name="bud_todos")
    op.drop_table("bud_todos")
