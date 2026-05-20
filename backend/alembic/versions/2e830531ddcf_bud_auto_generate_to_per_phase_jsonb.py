"""bud auto_generate to per-phase JSONB

Replace the single ``auto_generate`` bool on ``bud_documents`` with a
JSONB ``auto_generate_phases`` map (``{bud, design, tech_arch, testing}``
→ bool). New BUDs default to NULL/empty = all phases skip; existing
rows are backfilled so any pipeline already in-flight doesn't silently
stop mid-stage.

Revision ID: 2e830531ddcf
Revises: 29fbe5000c91
Create Date: 2026-05-20 22:24:38.149256

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2e830531ddcf"
down_revision: str | None = "29fbe5000c91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add the new JSONB column nullable so existing rows survive.
    op.add_column(
        "bud_documents",
        sa.Column("auto_generate_phases", postgresql.JSONB, nullable=True),
    )

    # 2. Backfill behaviour from the old bool:
    #    auto_generate=true  → all four phases enabled (preserves the
    #                          prior auto-fire-everything behaviour)
    #    auto_generate=false → NULL (= all phases skip, matches the new
    #                          empty-dict default for fresh inserts)
    op.execute(
        """
        UPDATE bud_documents
           SET auto_generate_phases = jsonb_build_object(
                   'bud', true,
                   'design', true,
                   'tech_arch', true,
                   'testing', true
               )
         WHERE auto_generate = true
        """
    )

    # 3. Drop the old column.
    op.drop_column("bud_documents", "auto_generate")


def downgrade() -> None:
    # Restore the bool column, default true to match the old behaviour.
    op.add_column(
        "bud_documents",
        sa.Column(
            "auto_generate",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    # Best-effort recovery: any row with at least one phase enabled
    # becomes auto_generate=true; a NULL or empty dict becomes false.
    op.execute(
        """
        UPDATE bud_documents
           SET auto_generate = CASE
                   WHEN auto_generate_phases IS NULL THEN false
                   WHEN auto_generate_phases = '{}'::jsonb THEN false
                   ELSE true
               END
        """
    )
    op.drop_column("bud_documents", "auto_generate_phases")
