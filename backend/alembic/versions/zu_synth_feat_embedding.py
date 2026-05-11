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

"""Add embedding column to synthesized_features.

The merge phase clusters unmerged synth rows by cosine similarity to
group likely-duplicates into focused Claude calls. Persisting the
embedding once at synthesis write-time avoids recomputing it on every
merge sweep and lets pgvector handle nearest-neighbour lookups via
``find_nearest_unmerged``. Same dim (384) as ``KnowledgeItem.embedding``
so promoted KIs can copy the synth row's vector without re-embedding.

Revision ID: zu_synth_feat_embedding
Revises: zt_synth_cache_updated_at
Create Date: 2026-04-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "zu_synth_feat_embedding"
down_revision: str | None = "zt_synth_cache_updated_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE synthesized_features ADD COLUMN embedding vector(384)")
    # HNSW with cosine ops — same shape as the existing KnowledgeItem,
    # bug, etc. indexes set up in the initial schema migration.
    op.execute(
        "CREATE INDEX ix_synth_feat_embedding ON synthesized_features "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_synth_feat_embedding")
    op.execute("ALTER TABLE synthesized_features DROP COLUMN IF EXISTS embedding")
