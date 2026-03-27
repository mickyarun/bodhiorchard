"""Drop bud_commits table and add indexes for dev_activity_logs commit queries.

Revision ID: a3f7b2c1d4e5
Revises: 11d8392f4c09
Create Date: 2026-03-27 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f7b2c1d4e5"
down_revision: str | None = "11d8392f4c09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add commit query indexes, then drop bud_commits."""
    # 1. Composite index for commit queries by BUD
    op.create_index(
        "ix_dev_activity_bud_event_type",
        "dev_activity_logs",
        ["bud_id", "event_type"],
    )

    # 2. Deduplicate existing commit rows before adding unique index.
    #    Keep the earliest row per (org_id, commit_sha), delete the rest.
    op.execute(sa.text("""
        DELETE FROM dev_activity_logs
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY org_id, commit_sha
                           ORDER BY created_at ASC
                       ) AS rn
                FROM dev_activity_logs
                WHERE event_type = 'commit' AND commit_sha IS NOT NULL
            ) dupes
            WHERE rn > 1
        )
    """))

    # 3. Partial unique index for commit dedup
    op.create_index(
        "uq_dev_activity_org_commit_sha",
        "dev_activity_logs",
        ["org_id", "commit_sha"],
        unique=True,
        postgresql_where=sa.text("event_type = 'commit' AND commit_sha IS NOT NULL"),
    )

    # 3. Drop bud_commits table (indexes dropped automatically)
    op.drop_table("bud_commits")


def downgrade() -> None:
    """Recreate bud_commits table and remove indexes."""
    op.create_table(
        "bud_commits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("bud_id", sa.UUID(), nullable=False),
        sa.Column("repo_path", sa.String(1000), nullable=False),
        sa.Column("branch_name", sa.String(500), nullable=False),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("commit_message", sa.String(500), nullable=False),
        sa.Column("files_changed", sa.String(5000), nullable=True),
        sa.Column("author_name", sa.String(255), nullable=True),
        sa.Column("author_email", sa.String(255), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["bud_id"], ["bud_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("org_id", "commit_sha", name="uq_bud_commit_org_sha"),
    )
    op.create_index("ix_bud_commit_bud_id", "bud_commits", ["bud_id"])
    op.create_index("ix_bud_commit_org_repo", "bud_commits", ["org_id", "repo_path"])
    op.create_index("ix_bud_commit_user_id", "bud_commits", ["user_id"])

    op.drop_index("uq_dev_activity_org_commit_sha", table_name="dev_activity_logs")
    op.drop_index("ix_dev_activity_bud_event_type", table_name="dev_activity_logs")
