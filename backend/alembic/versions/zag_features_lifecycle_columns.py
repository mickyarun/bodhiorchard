"""Features lifecycle columns + cluster_cache.signature.

Schema changes that unblock the reconciler-based incremental update
model. Three independent additions:

1. ``cluster_cache.signature VARCHAR(64) NOT NULL DEFAULT ''`` — the
   indexer now emits a SHA-256 of each cluster's canonical node-ID
   list (see ``app.services.code_indexer.seed.cluster_signature``).
   Existing rows backfill with the empty string; the next scan
   repopulates them with real values via the ingest stage.

2. ``features`` gains seven columns to support soft-delete + identity
   matching:

   * ``is_active BOOLEAN NOT NULL DEFAULT TRUE``
   * ``deactivated_at TIMESTAMPTZ NULL`` (stamped when ``is_active``
     flips to false)
   * ``last_seen_sha VARCHAR(64) NULL`` (head SHA at the last
     reconcile that confirmed the row is still present)
   * ``cluster_signature VARCHAR(64) NOT NULL`` (reconciler primary
     identity key — backfilled with ``id::text`` so existing rows are
     unique-per-row and the next synthesis run replaces them)
   * ``source VARCHAR(32) NULL`` (provenance: ``'scan'``, ``'bud'``,
     ``'mcp'``)
   * ``source_ref VARCHAR(500) NULL`` (free-form provenance reference)
   * ``feature_status VARCHAR(20) NULL`` (BUD lifecycle:
     ``planned``/``in_progress``/``implemented``)

3. ``features`` indexes are reshuffled: ``ix_feature_org_title`` is
   replaced by ``ix_feature_org_active_title`` (active-aware), and
   five additional indexes match the new query patterns:
   ``(org_id, is_active)``, ``(org_id, is_active, source)``,
   ``(org_id, is_active, feature_status)``, ``(org_id, source_ref)``,
   ``(org_id, cluster_signature)``.

Idempotent inspector pattern matches ``zaf``.

Revision ID: zag_features_lifecycle_columns
Revises: zaf_drop_feature_superseded_at
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "zag_features_lifecycle_columns"
down_revision: str | None = "zaf_drop_feature_superseded_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FEATURES = "features"
_CLUSTER_CACHE = "cluster_cache"
_OLD_INDEX = "ix_feature_org_title"
_NEW_INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ix_feature_org_active", ("org_id", "is_active")),
    ("ix_feature_org_active_title", ("org_id", "is_active", "feature_title")),
    ("ix_feature_org_active_source", ("org_id", "is_active", "source")),
    ("ix_feature_org_active_fstatus", ("org_id", "is_active", "feature_status")),
    ("ix_feature_org_srcref", ("org_id", "source_ref")),
    ("ix_feature_org_cluster_sig", ("org_id", "cluster_signature")),
)


def upgrade() -> None:
    """Add columns + indexes; backfill ``cluster_signature`` with ``id::text``."""
    bind = op.get_bind()
    inspector = inspect(bind)

    if _CLUSTER_CACHE in inspector.get_table_names():
        cc_cols = {c["name"] for c in inspector.get_columns(_CLUSTER_CACHE)}
        if "signature" not in cc_cols:
            op.add_column(
                _CLUSTER_CACHE,
                sa.Column(
                    "signature",
                    sa.String(64),
                    nullable=False,
                    server_default="",
                ),
            )

    if _FEATURES not in inspector.get_table_names():
        return

    feat_cols = {c["name"] for c in inspector.get_columns(_FEATURES)}

    if "is_active" not in feat_cols:
        op.add_column(
            _FEATURES,
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )
    if "deactivated_at" not in feat_cols:
        op.add_column(
            _FEATURES,
            sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "last_seen_sha" not in feat_cols:
        op.add_column(_FEATURES, sa.Column("last_seen_sha", sa.String(64), nullable=True))
    if "cluster_signature" not in feat_cols:
        # Add nullable, backfill, then enforce NOT NULL. Backfill uses
        # ``id::text`` so each existing row gets a unique placeholder
        # signature — guarantees no false-positive matches in the
        # reconciler before the next synthesis run rewrites them.
        op.add_column(
            _FEATURES,
            sa.Column("cluster_signature", sa.String(64), nullable=True),
        )
        op.execute(
            sa.text(
                f"UPDATE {_FEATURES} SET cluster_signature = id::text "  # noqa: S608
                "WHERE cluster_signature IS NULL"
            )
        )
        op.alter_column(_FEATURES, "cluster_signature", nullable=False)
    if "source" not in feat_cols:
        op.add_column(_FEATURES, sa.Column("source", sa.String(32), nullable=True))
    if "source_ref" not in feat_cols:
        op.add_column(_FEATURES, sa.Column("source_ref", sa.String(500), nullable=True))
    if "feature_status" not in feat_cols:
        op.add_column(_FEATURES, sa.Column("feature_status", sa.String(20), nullable=True))

    indexes = {ix["name"] for ix in inspector.get_indexes(_FEATURES)}
    if _OLD_INDEX in indexes:
        op.drop_index(_OLD_INDEX, table_name=_FEATURES)
    for name, cols in _NEW_INDEXES:
        if name not in indexes:
            op.create_index(name, _FEATURES, list(cols))


def downgrade() -> None:
    """Drop the new indexes + columns; restore the old title index."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if _FEATURES in inspector.get_table_names():
        indexes = {ix["name"] for ix in inspector.get_indexes(_FEATURES)}
        for name, _cols in _NEW_INDEXES:
            if name in indexes:
                op.drop_index(name, table_name=_FEATURES)
        if _OLD_INDEX not in indexes:
            op.create_index(_OLD_INDEX, _FEATURES, ["org_id", "feature_title"])

        feat_cols = {c["name"] for c in inspector.get_columns(_FEATURES)}
        for col in (
            "feature_status",
            "source_ref",
            "source",
            "cluster_signature",
            "last_seen_sha",
            "deactivated_at",
            "is_active",
        ):
            if col in feat_cols:
                op.drop_column(_FEATURES, col)

    if _CLUSTER_CACHE in inspector.get_table_names():
        cc_cols = {c["name"] for c in inspector.get_columns(_CLUSTER_CACHE)}
        if "signature" in cc_cols:
            op.drop_column(_CLUSTER_CACHE, "signature")
