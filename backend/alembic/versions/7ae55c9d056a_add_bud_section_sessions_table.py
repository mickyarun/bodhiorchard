"""add bud_section_sessions table

Revision ID: 7ae55c9d056a
Revises: e8ab2240ee91
Create Date: 2026-05-14 17:28:26.262059

Originating-agent Claude CLI session tracking per BUD section. One row
per ``(bud_id, section[, design_id])``: the AI agent that authors a
section claims a session id, and subsequent chats ``--resume`` against
the same id. Two partial unique indexes cover the same intent as a
single ``UNIQUE NULLS NOT DISTINCT`` constraint without requiring PG 15+
(SQL's ``NULL != NULL`` would otherwise let duplicate non-design rows
slip through because they all carry ``design_id=NULL``).

Inspected after ``alembic revision --autogenerate``. Stripped from the
autogen output: nine ``drop_table('xlm_*')`` calls (unrelated POC
artifacts still resident in the local dev DB) and one
``drop_column('roles', 'base_role')`` (covered by the parent migration
``e8ab2240ee91``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7ae55c9d056a"
down_revision: str | None = "e8ab2240ee91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bud_section_sessions",
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("bud_id", sa.UUID(), nullable=False),
        sa.Column("section", sa.String(length=30), nullable=False),
        sa.Column("design_id", sa.UUID(), nullable=True),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["design_id"], ["bud_designs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_bud_section_sessions_org_id"),
        "bud_section_sessions",
        ["org_id"],
        unique=False,
    )
    op.create_index(
        "uq_bud_section_sessions_bud_section",
        "bud_section_sessions",
        ["bud_id", "section"],
        unique=True,
        postgresql_where=sa.text("design_id IS NULL"),
    )
    op.create_index(
        "uq_bud_section_sessions_bud_section_design",
        "bud_section_sessions",
        ["bud_id", "section", "design_id"],
        unique=True,
        postgresql_where=sa.text("design_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_bud_section_sessions_bud_section_design",
        table_name="bud_section_sessions",
        postgresql_where=sa.text("design_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_bud_section_sessions_bud_section",
        table_name="bud_section_sessions",
        postgresql_where=sa.text("design_id IS NULL"),
    )
    op.drop_index(
        op.f("ix_bud_section_sessions_org_id"),
        table_name="bud_section_sessions",
    )
    op.drop_table("bud_section_sessions")
