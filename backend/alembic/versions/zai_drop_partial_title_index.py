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

"""Drop ``ux_ftr_primary_title`` — identity is now ``cluster_signature``.

Under the legacy wipe-on-resynth model the partial unique index
``ux_ftr_primary_title (repo_id, feature_title) WHERE role='primary'``
was the only structural guard against duplicate titles per repo. With
the reconciler's signature-based identity the index becomes a hazard:

* The LLM can legitimately emit two distinct features with the same
  title under different ``cluster_signature``s. The reconciler treats
  them as separate features (different signatures); the index would
  block the second insert.
* On revival, the reconciler reactivates an inactive row whose
  PRIMARY junction ``feature_title`` collides with a newer active row
  bearing the same title — also blocked by the index.

We rely on (a) the unique constraint ``(feature_id, repo_id)`` (no two
junctions per feature/repo pair) and (b) the reconciler's per-batch
``matched_ids`` set to prevent two synthesised entries from collapsing
onto one row. Title is now a display attribute, not an identity key.

Revision ID: zai_drop_partial_title_index
Revises: zah_drop_knowledge_tables
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "zai_drop_partial_title_index"
down_revision: str | None = "zah_drop_knowledge_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE = "feature_to_repo"
_INDEX = "ux_ftr_primary_title"


def upgrade() -> None:
    """Drop the partial unique index if present."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name=_TABLE)


def downgrade() -> None:
    """Re-create the partial unique index.

    Restores the legacy wipe-on-resynth invariant. Only safe when no
    duplicate ``(repo_id, feature_title)`` PRIMARY rows exist — the
    reconciler may have created them, in which case this DDL fails
    and an admin must dedupe by title before downgrading.
    """
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    if _INDEX in indexes:
        return
    op.create_index(
        _INDEX,
        _TABLE,
        ["repo_id", "feature_title"],
        unique=True,
        postgresql_where=sa.text("role = 'primary'"),
    )
