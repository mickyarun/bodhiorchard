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
