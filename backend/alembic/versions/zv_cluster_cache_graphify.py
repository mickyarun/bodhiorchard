"""Rename gitnexus_community_cache → cluster_cache, add symbols + repo_graph_cache.

Bodhiorchard is dropping its GitNexus dependency in favour of the MIT-licensed
graphify library, which drives clustering through tree-sitter + NetworkX +
Leiden. The on-disk schema needs three changes:

1. Rename ``gitnexus_community_cache`` → ``cluster_cache`` and rename
   ``community_id`` → ``cluster_id``. The other columns (label,
   heuristic_label, symbol_count, cohesion, files) carry over verbatim
   because graphify produces the same data shape.
2. Add ``cluster_cache.symbols JSONB`` so the new ``code_impact`` MCP tools
   can list a cluster's symbol names without round-tripping the graph blob.
3. Add ``repo_graph_cache(repo_id, head_sha, graph_json bytea, ...)``: one
   row per (repo, head_sha) holding the gzipped node-link JSON of the full
   call graph. Backs the new ``code_impact``/``code_query``/``code_context``
   MCP handlers. JSON-only on the wire — no binary serialisation formats
   that could enable arbitrary code execution on read.

Revision ID: zv_cluster_cache_graphify
Revises: zu_synth_feat_embedding
Create Date: 2026-04-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "zv_cluster_cache_graphify"
down_revision: str | None = "zu_synth_feat_embedding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("gitnexus_community_cache", "cluster_cache")
    op.alter_column("cluster_cache", "community_id", new_column_name="cluster_id")

    op.add_column(
        "cluster_cache",
        sa.Column(
            "symbols",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    op.execute("ALTER INDEX ix_gncc_repo_sha RENAME TO ix_cc_repo_sha")
    # Old unique key was ``(repo_id, head_sha, community_id)``; replace it
    # with an org-leading version so the constraint matches the rest of
    # the multi-tenant schema and a forgotten ``org_id`` filter elsewhere
    # cannot accidentally cross tenants.
    op.execute("ALTER TABLE cluster_cache DROP CONSTRAINT uq_gncc_repo_sha_community")
    op.create_unique_constraint(
        "uq_cc_repo_sha_cluster",
        "cluster_cache",
        ["org_id", "repo_id", "head_sha", "cluster_id"],
    )

    op.create_table(
        "repo_graph_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "repo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracked_repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("head_sha", sa.String(40), nullable=False),
        sa.Column("graph_json", sa.LargeBinary, nullable=False),
        sa.Column("node_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("edge_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "org_id",
            "repo_id",
            "head_sha",
            name="uq_repo_graph_cache_repo_sha",
        ),
    )
    op.create_index(
        "ix_repo_graph_cache_repo_sha",
        "repo_graph_cache",
        ["repo_id", "head_sha"],
    )


def downgrade() -> None:
    op.drop_index("ix_repo_graph_cache_repo_sha", table_name="repo_graph_cache")
    op.drop_table("repo_graph_cache")

    op.execute("ALTER INDEX ix_cc_repo_sha RENAME TO ix_gncc_repo_sha")
    op.drop_constraint("uq_cc_repo_sha_cluster", "cluster_cache", type_="unique")
    op.create_unique_constraint(
        "uq_gncc_repo_sha_community",
        "cluster_cache",
        ["repo_id", "head_sha", "cluster_id"],
    )

    op.drop_column("cluster_cache", "symbols")
    op.alter_column("cluster_cache", "cluster_id", new_column_name="community_id")
    op.rename_table("cluster_cache", "gitnexus_community_cache")
