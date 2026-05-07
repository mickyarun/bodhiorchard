"""Rename synthesized_features → features + create feature_to_repo junction.

The single ``repo_id`` FK on the synthesis row is replaced by a
many-to-many junction so a feature can link to its source repo
(``role=primary``) and any number of backend repos whose routes it
calls (``role=backend``). The latter is populated by the new
``backend_link`` per-repo stage.

Step order matters: rename FIRST (Postgres updates self-FK
``merged_into_id`` automatically), then build & backfill the junction,
THEN drop the now-redundant columns from the renamed table. Running
``drop_column`` before backfill would lose the ``code_locations`` data
needed to seed the PRIMARY junction rows.

Revision ID: zy_features_join_table
Revises: zx_repo_layer
Create Date: 2026-05-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zy_features_join_table"
down_revision: str | None = "zx_repo_layer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ROLE_VALUES = ("primary", "backend")


def upgrade() -> None:
    """Rename, build the junction, backfill, drop the redundant columns.

    Every step is wrapped in IF [NOT] EXISTS-style guards so a previous
    half-applied attempt (the autocommit DDL hazard with asyncpg) doesn't
    block re-runs. The transaction either advances cleanly or no-ops.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Rename the table if the new name doesn't already exist. Self-FK
    #    ``merged_into_id`` follows automatically.
    table_names = set(inspector.get_table_names())
    if "synthesized_features" in table_names and "features" not in table_names:
        op.rename_table("synthesized_features", "features")
        table_names = set(inspector.get_table_names())

    # 2. Index swap. ``CREATE INDEX IF NOT EXISTS`` + ``DROP INDEX IF EXISTS``
    #    keep this idempotent across partial runs.
    for old_name in (
        "ix_synth_feat_scan_repo",
        "ix_synth_feat_repo_title",
        "ix_synth_feat_merged_into",
        "ix_synth_feat_latest",
        "ix_synth_feat_scan_outcome",
    ):
        op.execute(f"DROP INDEX IF EXISTS {old_name}")

    op.execute("CREATE INDEX IF NOT EXISTS ix_feature_scan ON features (scan_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_feature_org_title ON features (org_id, feature_title)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_feature_merged_into ON features (merged_into_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_feature_latest ON features (org_id) "
        "WHERE superseded_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_feature_scan_outcome ON features (scan_id, merge_outcome)"
    )

    # 3. Create the role enum via DO block so re-runs don't hit
    #    DuplicateObjectError. The column reference below uses
    #    ``create_type=False`` so the table create won't try again.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'feature_to_repo_role') THEN
                CREATE TYPE feature_to_repo_role AS ENUM ('primary', 'backend');
            END IF;
        END$$;
        """
    )
    if "feature_to_repo" not in table_names:
        # ``postgresql.ENUM`` (dialect-specific) reliably honours
        # ``create_type=False`` from inside ``op.create_table``;
        # ``sa.Enum`` does not — it re-emits CREATE TYPE despite the
        # flag, which collides with the DO-block guard above.
        role_type = sa.dialects.postgresql.ENUM(
            *_ROLE_VALUES, name="feature_to_repo_role", create_type=False
        )
        op.create_table(
            "feature_to_repo",
            sa.Column(
                "id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "feature_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey("features.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "repo_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tracked_repositories.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("role", role_type, nullable=False),
            sa.Column("code_locations", sa.dialects.postgresql.JSONB(), nullable=True),
            sa.Column(
                "api_paths",
                sa.dialects.postgresql.ARRAY(sa.String()),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("feature_id", "repo_id", name="uq_ftr_feature_repo"),
        )
    op.execute("CREATE INDEX IF NOT EXISTS ix_ftr_feature_id ON feature_to_repo (feature_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ftr_repo_id ON feature_to_repo (repo_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ftr_feature_role ON feature_to_repo (feature_id, role)"
    )

    # 4. Backfill PRIMARY junction rows. The ON CONFLICT guard makes
    #    re-runs safe: a partial backfill that committed before the drop
    #    columns step won't double-insert.
    feature_columns = {col["name"] for col in inspector.get_columns("features")}
    if "repo_id" in feature_columns:
        op.execute(
            """
            INSERT INTO feature_to_repo (feature_id, repo_id, role, code_locations)
            SELECT id, repo_id, 'primary'::feature_to_repo_role, code_locations
            FROM features
            WHERE repo_id IS NOT NULL
            ON CONFLICT (feature_id, repo_id) DO NOTHING
            """
        )

    # 5. Drop the now-redundant columns from features (idempotent).
    if "code_locations" in feature_columns:
        op.drop_column("features", "code_locations")
    if "repo_id" in feature_columns:
        op.drop_column("features", "repo_id")


def downgrade() -> None:
    """Reverse — restore ``repo_id`` + ``code_locations``, drop the junction.

    PRIMARY rows in the junction are the source of truth for the restored
    columns; BACKEND rows are dropped (they had no representation in the
    pre-migration schema).
    """
    op.add_column(
        "features",
        sa.Column(
            "repo_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "features",
        sa.Column(
            "code_locations",
            sa.dialects.postgresql.JSONB(),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE features
        SET repo_id = j.repo_id, code_locations = j.code_locations
        FROM feature_to_repo j
        WHERE j.feature_id = features.id AND j.role = 'primary'
        """
    )
    op.execute("UPDATE features SET code_locations = '{}'::jsonb WHERE code_locations IS NULL")
    op.alter_column(
        "features",
        "code_locations",
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    op.create_foreign_key(
        "fk_features_repo_id",
        "features",
        "tracked_repositories",
        ["repo_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("features", "repo_id", nullable=False)

    op.drop_index("ix_ftr_feature_role", table_name="feature_to_repo")
    op.drop_index("ix_ftr_repo_id", table_name="feature_to_repo")
    op.drop_index("ix_ftr_feature_id", table_name="feature_to_repo")
    op.drop_table("feature_to_repo")
    sa.Enum(name="feature_to_repo_role").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_feature_scan_outcome", table_name="features")
    op.drop_index("ix_feature_latest", table_name="features")
    op.drop_index("ix_feature_merged_into", table_name="features")
    op.drop_index("ix_feature_org_title", table_name="features")
    op.drop_index("ix_feature_scan", table_name="features")

    op.create_index("ix_synth_feat_scan_outcome", "features", ["scan_id", "merge_outcome"])
    op.create_index(
        "ix_synth_feat_latest",
        "features",
        ["org_id", "repo_id"],
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.create_index("ix_synth_feat_merged_into", "features", ["merged_into_id"])
    op.create_index("ix_synth_feat_repo_title", "features", ["org_id", "repo_id", "feature_title"])
    op.create_index("ix_synth_feat_scan_repo", "features", ["scan_id", "repo_id"])

    op.rename_table("features", "synthesized_features")
