"""Drop ``knowledge_to_repo`` and ``knowledge_items``.

The legacy knowledge tables are retired in favour of ``features`` +
``feature_to_repo``. The new tables already carry every load-bearing
column (the column-parity audit identified seven columns to add to
``features`` — handled by the prior revision ``zag``).

**Data is unrecoverable.** This is a pre-prod local-dev cut: no users,
no migration of row-level data. The downgrade re-creates an empty
shell of each table so a code rollback can run without crashing on
import, but the rows themselves are gone for good.

Drop order respects the FK chain: ``knowledge_to_repo`` first
(``knowledge_id`` → ``knowledge_items.id``), then ``knowledge_items``.

Revision ID: zah_drop_knowledge_tables
Revises: zag_features_lifecycle_columns
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "zah_drop_knowledge_tables"
down_revision: str | None = "zag_features_lifecycle_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_KRL = "knowledge_to_repo"
_KI = "knowledge_items"


def upgrade() -> None:
    """Repoint dangling FKs, then drop the junction + parent table.

    ``skill_profiles.feature_id`` previously pointed at
    ``knowledge_items.id`` (with ``ON DELETE SET NULL``). Repoint it
    at ``features.id`` before dropping ``knowledge_items``. Existing
    rows whose old feature_id no longer maps to a real ``features.id``
    are NULL'd as part of the FK switch — pre-prod local-dev, no row
    preservation guarantee.
    """
    bind = op.get_bind()
    inspector = inspect(bind)

    # Switch skill_profiles.feature_id FK from knowledge_items → features.
    if "skill_profiles" in inspector.get_table_names():
        fks = inspector.get_foreign_keys("skill_profiles")
        for fk in fks:
            if (
                fk.get("referred_table") == _KI
                and fk.get("constrained_columns") == ["feature_id"]
            ):
                op.drop_constraint(fk["name"], "skill_profiles", type_="foreignkey")
        # NULL out feature_ids that don't exist in features (data is
        # unrecoverable; preserves NULLability and FK integrity).
        op.execute(
            sa.text(
                "UPDATE skill_profiles SET feature_id = NULL "
                "WHERE feature_id IS NOT NULL "
                "AND feature_id NOT IN (SELECT id FROM features)"
            )
        )
        op.create_foreign_key(
            "skill_profiles_feature_id_fkey",
            "skill_profiles",
            "features",
            ["feature_id"],
            ["id"],
            ondelete="SET NULL",
        )

    tables = set(inspector.get_table_names())
    if _KRL in tables:
        op.drop_table(_KRL)
    if _KI in tables:
        op.drop_table(_KI)


def downgrade() -> None:
    """Re-create empty shells. Row-level data is not restorable.

    Schema mirrors the model definitions in the deleted
    ``app.models.knowledge_item`` so an older code revision can compile
    and import without crashing on missing tables. The indexes and
    pgvector column are recreated; the rows are not.
    """
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if _KI not in tables:
        op.create_table(
            _KI,
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "org_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey("organizations.id"),
                nullable=False,
            ),
            sa.Column("category", sa.String(255), nullable=False),
            sa.Column("title", sa.String(500), nullable=False),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("source", sa.String(255), nullable=True),
            sa.Column("source_ref", sa.String(500), nullable=True),
            sa.Column("tags", sa.dialects.postgresql.ARRAY(sa.String()), nullable=True),
            sa.Column("embedding", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("feature_status", sa.String(20), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_ki_org_cat_active", _KI, ["org_id", "category", "is_active"])

    if _KRL not in tables:
        op.create_table(
            _KRL,
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "knowledge_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey(f"{_KI}.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "repo_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tracked_repositories.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("code_locations", sa.JSON(), nullable=True),
            sa.UniqueConstraint("knowledge_id", "repo_id", name="uq_krl_knowledge_repo"),
        )
        op.create_index("ix_krl_repo_id", _KRL, ["repo_id"])
