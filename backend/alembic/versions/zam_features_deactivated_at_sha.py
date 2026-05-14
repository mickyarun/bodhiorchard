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

"""Add ``features.deactivated_at_sha`` for commit-attributable inactivation.

The PR-merge / scan reconciler now records the head SHA at which it
soft-deletes a feature row. Pair with ``deactivated_at`` (timestamp) to
surface "BUD-021 deactivated by commit abc1234" in the UI.

Cleared on revive (see :meth:`FeatureRepository.revive`).

Idempotent inspector pattern matches sibling migrations (``zag``).

Revision ID: zam_features_deactivated_at_sha
Revises: 88f86e7e5e03
Create Date: 2026-05-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "zam_features_deactivated_at_sha"
down_revision: str | None = "88f86e7e5e03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FEATURES = "features"
_COL = "deactivated_at_sha"


def upgrade() -> None:
    """Add ``deactivated_at_sha VARCHAR(64) NULL``. Idempotent."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if _FEATURES not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns(_FEATURES)}
    if _COL not in cols:
        op.add_column(_FEATURES, sa.Column(_COL, sa.String(64), nullable=True))


def downgrade() -> None:
    """Drop the column. Safe — values are non-load-bearing once dropped."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if _FEATURES in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns(_FEATURES)}
        if _COL in cols:
            op.drop_column(_FEATURES, _COL)
