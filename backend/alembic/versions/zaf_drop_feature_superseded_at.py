"""Drop ``features.superseded_at`` and the ``ix_feature_latest`` partial index.

Phase C of the lifecycle simplification. The synthesise stage now wipes
every feature whose PRIMARY junction points at the repo before
re-synthesis (Phase A), and the partial unique index on ``feature_to_repo
(repo_id, feature_title) WHERE role='primary'`` enforces uniqueness at
the DB level. Neither relies on ``superseded_at`` — the column was the
last vestige of the deleted Claude-driven merge phase.

Sequence:

1. Drop the partial index ``ix_feature_latest`` (its predicate
   referenced the column).
2. Drop the column.

Idempotent inspector pattern matching ``zad`` / ``zae``.

Revision ID: zaf_drop_feature_superseded_at
Revises: zae_feature_to_repo_title_denorm
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "zaf_drop_feature_superseded_at"
down_revision: str | None = "zae_feature_to_repo_title_denorm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE = "features"
_INDEX_NAME = "ix_feature_latest"
_COLUMN = "superseded_at"


def upgrade() -> None:
    """Drop the partial index, then the column."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    if _INDEX_NAME in indexes:
        op.drop_index(_INDEX_NAME, table_name=_TABLE)

    cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _COLUMN in cols:
        op.drop_column(_TABLE, _COLUMN)


def downgrade() -> None:
    """Restore the column as nullable + recreate the partial index.

    One-way trip on the data side. ``superseded_at`` carried the
    history of which feature rows had been replaced by re-synthesis;
    that history can't be reconstructed after a Phase A wipe-on-resynth
    has run because the prior rows are gone. The downgrade restores the
    *shape* (nullable column + partial index) so the model can compile
    against an older revision, but every row reads as "current"
    (NULL) — code rolled back to a pre-Phase-A revision must accept
    that outcome.
    """
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _COLUMN not in cols:
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.DateTime(timezone=True), nullable=True),
        )

    indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    if _INDEX_NAME not in indexes:
        op.create_index(
            _INDEX_NAME,
            _TABLE,
            ["org_id"],
            postgresql_where=sa.text(f"{_COLUMN} IS NULL"),
        )
