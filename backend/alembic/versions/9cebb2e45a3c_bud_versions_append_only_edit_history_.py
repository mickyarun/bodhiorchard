"""bud_versions: append-only edit history with per-phase ring buffer

Revision ID: 9cebb2e45a3c
Revises: af34446bb2fe
Create Date: 2026-05-21 11:16:23.047030

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9cebb2e45a3c"
down_revision: str | None = "af34446bb2fe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the append-only ``bud_versions`` table and backfill a v1 row per
    existing BUD so the History tab is non-empty from the first deploy.
    """
    # ``bud_status`` already exists from the BUDDocument migration; we
    # reuse it via ``create_type=False`` so the migration doesn't try to
    # CREATE TYPE a second time.
    bud_status = postgresql.ENUM(
        "bud",
        "design",
        "tech_arch",
        "development",
        "code_review",
        "testing",
        "uat",
        "prod",
        "closed",
        "discarded",
        name="bud_status",
        create_type=False,
    )
    bud_edit_source = postgresql.ENUM(
        "ui", "mcp", "agent", "migration", "revert", name="bud_edit_source"
    )
    bud_edit_source.create(op.get_bind(), checkfirst=True)
    # Reuse the type just created — passing the ENUM to ``create_table``
    # without this would try to CREATE TYPE a second time and fail.
    bud_edit_source_ref = postgresql.ENUM(
        "ui",
        "mcp",
        "agent",
        "migration",
        "revert",
        name="bud_edit_source",
        create_type=False,
    )

    op.create_table(
        "bud_versions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("bud_id", sa.UUID(), nullable=False),
        sa.Column("phase", bud_status, nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", bud_edit_source_ref, nullable=False),
        sa.Column("edited_by", sa.UUID(), nullable=True),
        sa.Column("mcp_token_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "edited_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["bud_id"], ["bud_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["edited_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["mcp_token_id"], ["user_mcp_tokens.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("bud_id", "phase", "version_no", name="uq_bud_version_per_phase"),
    )
    op.create_index(
        "ix_bud_version_phase_latest", "bud_versions", ["bud_id", "phase", "version_no"]
    )
    op.create_index("ix_bud_version_recent", "bud_versions", ["bud_id", "edited_at"])

    # Backfill: one v1 snapshot per existing BUD using the current row
    # state and current status as the phase. ``source='migration'`` lets
    # operators distinguish these synthetic baselines from real edits in
    # the History tab; they're excluded from the per-phase prune cap
    # only when ``source != 'revert'``, which they already are.
    op.execute(
        sa.text(
            """
            INSERT INTO bud_versions (
                id, bud_id, phase, version_no, snapshot, source, edited_by,
                mcp_token_id, reason, edited_at
            )
            SELECT
                gen_random_uuid(),
                b.id,
                b.status,
                1,
                jsonb_build_object(
                    'title', b.title,
                    'requirements_md', b.requirements_md,
                    'tech_spec_md', b.tech_spec_md,
                    'test_plan_md', b.test_plan_md,
                    'qa_automation_cases', b.qa_automation_cases,
                    'qa_manual_cases', b.qa_manual_cases,
                    'qa_execution_plan_md', b.qa_execution_plan_md,
                    'code_review_comments', b.code_review_comments,
                    'assignee_id', CASE
                        WHEN b.assignee_id IS NULL THEN NULL
                        ELSE to_jsonb(b.assignee_id::text)
                    END,
                    'auto_generate_phases', b.auto_generate_phases,
                    'metadata_', b.metadata,
                    'impacted_repos', b.impacted_repos
                ),
                'migration',
                NULL,
                NULL,
                'initial backfill from bud_documents',
                NOW()
            FROM bud_documents b
            """
        )
    )


def downgrade() -> None:
    """Drop the table and the new enum. ``bud_status`` is left alone — it
    predates this migration."""
    op.drop_index("ix_bud_version_recent", table_name="bud_versions")
    op.drop_index("ix_bud_version_phase_latest", table_name="bud_versions")
    op.drop_table("bud_versions")
    bud_edit_source = postgresql.ENUM(name="bud_edit_source")
    bud_edit_source.drop(op.get_bind(), checkfirst=True)
