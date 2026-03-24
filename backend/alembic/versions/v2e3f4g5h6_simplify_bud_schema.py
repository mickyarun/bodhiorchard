"""Simplify BUD schema: rename content_md → requirements_md, drop redundant columns.

Revision ID: v2e3f4g5h6
Revises: u1d2e3f4g5
Create Date: 2026-03-21 14:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "v2e3f4g5h6"
down_revision = "u1d2e3f4g5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename content_md → requirements_md for clarity
    op.alter_column("bud_documents", "content_md", new_column_name="requirements_md")

    # Drop redundant design_md (bud_designs table is the source of truth)
    op.drop_column("bud_documents", "design_md")

    # Drop design_path from bud_designs (DB is single source of truth, no file sync)
    op.drop_column("bud_designs", "design_path")

    # Update chat message section values to match new names
    op.execute(
        "UPDATE bud_chat_messages SET section = 'requirements_md' WHERE section = 'content_md'"
    )
    op.execute("UPDATE bud_chat_messages SET section = 'design' WHERE section = 'design_md'")


def downgrade() -> None:
    op.alter_column("bud_documents", "requirements_md", new_column_name="content_md")
    op.add_column("bud_documents", sa.Column("design_md", sa.Text(), nullable=True))
    op.add_column("bud_designs", sa.Column("design_path", sa.String(500), nullable=True))
    op.execute(
        "UPDATE bud_chat_messages SET section = 'content_md' WHERE section = 'requirements_md'"
    )
    op.execute("UPDATE bud_chat_messages SET section = 'design_md' WHERE section = 'design'")
