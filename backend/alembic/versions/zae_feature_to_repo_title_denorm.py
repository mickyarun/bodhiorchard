"""Denormalise ``feature_title`` onto ``feature_to_repo`` + per-repo unique on PRIMARY.

After Phase A's wholesale-wipe-on-resynth in the synthesise stage, the
old ``supersede_prior_by_title`` safety net becomes redundant — but a
regression in the synthesis prompt that emits the same title twice in
one run would silently produce duplicate rows. A partial unique index on
``(repo_id, feature_title) WHERE role='primary'`` is the smallest
DB-level guard that catches it at write time without constraining
cross-repo title reuse.

Postgres unique indexes can't reference columns from another table, so
this migration denormalises ``feature_title`` onto ``feature_to_repo``.
``Feature.feature_title`` is immutable in the live pipeline, so the
denormalisation is safe to maintain.

Sequence:

1. Add ``feature_title`` as nullable.
2. Backfill from ``features`` for existing rows.
3. Promote to NOT NULL.
4. Create the partial unique index.

Each step is guarded so a partially-applied prior run is replayable.

Revision ID: zae_feature_to_repo_title_denorm
Revises: zad_drop_dead_feature_cols
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "zae_feature_to_repo_title_denorm"
down_revision: str | None = "zad_drop_dead_feature_cols"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_INDEX_NAME = "ux_ftr_primary_title"
_TABLE = "feature_to_repo"


def upgrade() -> None:
    """Add feature_title denorm column + partial unique index."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    if "feature_title" not in cols:
        op.add_column(
            _TABLE,
            sa.Column("feature_title", sa.String(length=500), nullable=True),
        )
        # Backfill from the parent ``features`` row. Safe to run twice —
        # the WHERE clause skips rows that already have a value.
        op.execute(
            "UPDATE feature_to_repo ftr "
            "SET feature_title = f.feature_title "
            "FROM features f "
            "WHERE ftr.feature_id = f.id "
            "  AND ftr.feature_title IS NULL"
        )
        op.alter_column(_TABLE, "feature_title", nullable=False)

    indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    if _INDEX_NAME not in indexes:
        # Pre-index cleanup: legacy ``supersede_prior_by_title`` only
        # marked the old ``features`` row as ``superseded_at IS NOT NULL``
        # — it never deleted that feature's PRIMARY junction. So today a
        # re-synthesised (repo, title) carries two PRIMARY junction rows:
        # one pointing at the new (current) feature and one at the old
        # (superseded) feature. The new partial unique index would refuse
        # to build with both still present. Deleting junctions whose
        # parent feature has ``superseded_at IS NOT NULL`` removes only
        # the *stale* side — the current feature has ``superseded_at IS
        # NULL`` and its junction stays. The cascade on
        # ``feature_to_repo.feature_id`` keeps consistency if the parent
        # feature is itself dropped later in Phase C.
        # Gated on ``_INDEX_NAME not in indexes`` so a replay of the
        # already-applied migration does NOT re-run the delete.
        op.execute(
            "DELETE FROM feature_to_repo ftr "
            "USING features f "
            "WHERE ftr.feature_id = f.id "
            "  AND f.superseded_at IS NOT NULL"
        )
        op.create_index(
            _INDEX_NAME,
            _TABLE,
            ["repo_id", "feature_title"],
            unique=True,
            postgresql_where=sa.text("role = 'primary'"),
        )


def downgrade() -> None:
    """Drop the index then the column.

    Order matters — the index references the column, so the column drop
    would otherwise fail. Both steps are guarded for replay safety.
    """
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    if _INDEX_NAME in indexes:
        op.drop_index(_INDEX_NAME, table_name=_TABLE)

    cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    if "feature_title" in cols:
        op.drop_column(_TABLE, "feature_title")
