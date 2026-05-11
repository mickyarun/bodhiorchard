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

"""Drop ``features.scan_id`` and the two scan-keyed indexes.

Features are now repo-scoped (``feature_to_repo`` PRIMARY junction
carries the repo binding); a single feature persists across re-scans
of the same repo via ``superseded_at``-based supersession instead of
being re-written per scan. The ``scan_id`` column was the only scan-
specific binding left on the row and stopped being read after the
serialise / coverage-audit / synth_feature_writer paths switched to
the per-repo grouping.

Idempotent: every drop is wrapped in an ``IF EXISTS`` guard so a
partially-applied prior run can be replayed safely.

Revision ID: zac_drop_feature_scan_id
Revises: zab_phase_enum_extract_routes
Create Date: 2026-05-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "zac_drop_feature_scan_id"
down_revision: str | None = "zab_phase_enum_extract_routes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the two scan-keyed indexes and the column itself."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if "features" not in inspector.get_table_names():
        return
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("features")}
    if "ix_feature_scan_outcome" in existing_indexes:
        op.drop_index("ix_feature_scan_outcome", table_name="features")
    if "ix_feature_scan" in existing_indexes:
        op.drop_index("ix_feature_scan", table_name="features")

    existing_columns = {c["name"] for c in inspector.get_columns("features")}
    if "scan_id" in existing_columns:
        op.drop_column("features", "scan_id")


def downgrade() -> None:
    """Restore the column + indexes as nullable.

    Re-creating the column as ``NOT NULL`` would fail against existing
    rows; downgrade leaves it nullable so the rollback unblocks. Re-
    upgrading drops the column again, so the asymmetry is contained.
    """
    bind = op.get_bind()
    inspector = inspect(bind)
    if "features" not in inspector.get_table_names():
        return
    existing_columns = {c["name"] for c in inspector.get_columns("features")}
    if "scan_id" not in existing_columns:
        op.add_column("features", sa.Column("scan_id", UUID(as_uuid=True), nullable=True))
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("features")}
    if "ix_feature_scan" not in existing_indexes:
        op.create_index("ix_feature_scan", "features", ["scan_id"])
    if "ix_feature_scan_outcome" not in existing_indexes:
        op.create_index("ix_feature_scan_outcome", "features", ["scan_id", "merge_outcome"])
