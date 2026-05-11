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

"""Drop repo column from skill_profiles

The repo relationship is now derived through the feature chain:
SkillProfile.feature_id → KnowledgeItem ← KnowledgeRepoLink → TrackedRepository

Revision ID: z7_drop_skill_profile_repo
Revises: z6a7b8c9d0_strip_repo_prefix_from_titles
Create Date: 2026-03-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "z7_drop_skill_profile_repo"
down_revision: str | None = "z6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the redundant repo column from skill_profiles."""
    op.drop_column("skill_profiles", "repo")


def downgrade() -> None:
    """Re-add repo column as nullable string."""
    op.add_column(
        "skill_profiles",
        sa.Column("repo", sa.String(length=500), nullable=True),
    )
