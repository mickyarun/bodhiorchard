# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Drop ``features.merge_outcome`` / ``merged_into_id`` / ``knowledge_item_id``.

The Claude-driven feature_merge global phase that wrote these columns
was removed several rounds ago; the live pipeline always passes
``None`` to all three. Their only readers are zero-call-site
helpers (now deleted) and a dead UI schema. Dropping them removes
~50 lines of dead synth-writer plumbing and stops new code leaning
on values nothing maintains.

Idempotent: every drop is wrapped in an ``IF EXISTS`` guard so a
partially-applied prior run can be replayed safely. Same shape as
``zac_drop_feature_scan_id``.

Revision ID: zad_drop_dead_feature_cols
Revises: zac_drop_feature_scan_id
Create Date: 2026-05-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "zad_drop_dead_feature_cols"
down_revision: str | None = "zac_drop_feature_scan_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the merge-phase index, the three dead columns, and the enum type."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if "features" not in inspector.get_table_names():
        return

    indexes = {ix["name"] for ix in inspector.get_indexes("features")}
    if "ix_feature_merged_into" in indexes:
        op.drop_index("ix_feature_merged_into", table_name="features")

    cols = {c["name"] for c in inspector.get_columns("features")}
    if "merge_outcome" in cols:
        op.drop_column("features", "merge_outcome")
    if "merged_into_id" in cols:
        op.drop_column("features", "merged_into_id")
    if "knowledge_item_id" in cols:
        op.drop_column("features", "knowledge_item_id")

    # The enum type backing ``merge_outcome``. Postgres won't drop a
    # type that has dependent columns, so this only succeeds after the
    # column drop above. ``IF EXISTS`` keeps it safe on re-runs.
    op.execute("DROP TYPE IF EXISTS synth_feat_merge_outcome")


def downgrade() -> None:
    """Restore the columns + index + enum as nullable.

    Re-creating with ``NOT NULL`` would fail against existing rows;
    downgrade leaves them nullable so the rollback unblocks. Same
    asymmetric handling as :mod:`zac_drop_feature_scan_id`.
    """
    bind = op.get_bind()
    inspector = inspect(bind)
    if "features" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("features")}

    # Recreate the enum first — required before the column re-add.
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'synth_feat_merge_outcome') THEN "
        "CREATE TYPE synth_feat_merge_outcome AS ENUM ('canonical', 'merged_into', 'unvisited'); "
        "END IF; END $$;"
    )

    if "knowledge_item_id" not in cols:
        op.add_column(
            "features",
            sa.Column(
                "knowledge_item_id",
                UUID(as_uuid=True),
                sa.ForeignKey("knowledge_items.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if "merged_into_id" not in cols:
        op.add_column(
            "features",
            sa.Column(
                "merged_into_id",
                UUID(as_uuid=True),
                sa.ForeignKey("features.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if "merge_outcome" not in cols:
        op.add_column(
            "features",
            sa.Column(
                "merge_outcome",
                sa.Enum(
                    "canonical",
                    "merged_into",
                    "unvisited",
                    name="synth_feat_merge_outcome",
                    create_type=False,
                ),
                nullable=True,
            ),
        )

    indexes = {ix["name"] for ix in inspector.get_indexes("features")}
    if "ix_feature_merged_into" not in indexes:
        op.create_index("ix_feature_merged_into", "features", ["merged_into_id"])
