"""reposcanv2: repo_meta_communities + feature_meta_communities

Revision ID: d12dfd234b12
Revises: zp_scans_table
Create Date: 2026-04-26 05:33:52.292598

Adds the v2 reduction-output table (``repo_meta_communities``) and the
feature-to-community linkage table (``feature_meta_communities``) plus
two new PG enum types (``community_processing_status``,
``feature_community_role``).

The legacy ``scan_phase`` enum is reused for ``stage_dropped_at``;
``create_type=False`` on the column tells SQLAlchemy not to issue
``CREATE TYPE`` again.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d12dfd234b12"
down_revision: str | None = "zp_scans_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_PROCESSING_STATUS_VALUES = ("pending", "in_synthesis", "consumed", "skipped")
_FEATURE_COMMUNITY_ROLE_VALUES = ("merged", "dropped", "skipped")


def upgrade() -> None:
    op.create_table(
        "repo_meta_communities",
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("repo_id", sa.UUID(), nullable=False),
        sa.Column("community_id", sa.String(length=128), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("symbol_count", sa.Integer(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("cohesion", sa.Float(), nullable=True),
        sa.Column(
            "files",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "source_community_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("dropped", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("drop_reason", sa.Text(), nullable=True),
        # Reuse existing scan_phase PG enum (declared by ScanPhaseCheckpoint
        # migration). create_type=False prevents a duplicate CREATE TYPE.
        sa.Column(
            "stage_dropped_at",
            postgresql.ENUM(name="scan_phase", create_type=False),
            nullable=True,
        ),
        sa.Column(
            "processing_status",
            sa.Enum(*_PROCESSING_STATUS_VALUES, name="community_processing_status"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("consumed_by_feature_id", sa.UUID(), nullable=True),
        sa.Column("head_sha", sa.String(length=40), nullable=False),
        sa.Column(
            "extras",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["consumed_by_feature_id"], ["knowledge_items.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["repo_id"], ["tracked_repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repo_id",
            "head_sha",
            "community_id",
            name="uq_repo_meta_repo_sha_community",
        ),
    )
    op.create_index(
        "ix_repo_meta_org_repo",
        "repo_meta_communities",
        ["org_id", "repo_id"],
        unique=False,
    )
    op.create_index(
        "ix_repo_meta_repo_sha_kept",
        "repo_meta_communities",
        ["repo_id", "head_sha"],
        unique=False,
        postgresql_where=sa.text("dropped = false"),
    )

    op.create_table(
        "feature_meta_communities",
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("feature_id", sa.UUID(), nullable=False),
        sa.Column("repo_meta_community_id", sa.UUID(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(*_FEATURE_COMMUNITY_ROLE_VALUES, name="feature_community_role"),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(["feature_id"], ["knowledge_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["repo_meta_community_id"],
            ["repo_meta_communities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "feature_id",
            "repo_meta_community_id",
            "role",
            name="uq_feature_meta_community_role",
        ),
    )
    op.create_index(
        "ix_feature_meta_community",
        "feature_meta_communities",
        ["repo_meta_community_id"],
        unique=False,
    )
    op.create_index(
        "ix_feature_meta_feature",
        "feature_meta_communities",
        ["feature_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_feature_meta_feature", table_name="feature_meta_communities")
    op.drop_index("ix_feature_meta_community", table_name="feature_meta_communities")
    op.drop_table("feature_meta_communities")
    op.drop_index(
        "ix_repo_meta_repo_sha_kept",
        table_name="repo_meta_communities",
        postgresql_where=sa.text("dropped = false"),
    )
    op.drop_index("ix_repo_meta_org_repo", table_name="repo_meta_communities")
    op.drop_table("repo_meta_communities")
    # Drop only the enum types this migration created. ``scan_phase`` is
    # owned by the earlier ScanPhaseCheckpoint migration.
    sa.Enum(name="feature_community_role").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="community_processing_status").drop(op.get_bind(), checkfirst=True)
