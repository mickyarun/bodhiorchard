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

"""Add tags column to synthesized_features.

Per-repo synthesis is now staging-only — the merge phase promotes
synth rows to ``knowledge_items``. Without a ``tags`` column on the
synth row, the search-keyword tags Claude emits during synthesis are
lost between staging and promotion. This migration adds the column so
``persist_synth_feature`` can stash tags and ``promote_synth_to_ki``
can carry them through to the canonical ``knowledge_items.tags`` array.

Revision ID: zr_synth_feat_tags
Revises: d8d4527c584e
Create Date: 2026-04-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "zr_synth_feat_tags"
down_revision: str | None = "d8d4527c584e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "synthesized_features",
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
    )


def downgrade() -> None:
    op.drop_column("synthesized_features", "tags")
