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

"""add impacted_repos and commit author fields

Revision ID: 73bce4e5a843
Revises: 49c94f23fd15
Create Date: 2026-03-26 12:19:40.436493

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "73bce4e5a843"
down_revision: str | None = "49c94f23fd15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # BUDDocument: add impacted_repos
    op.add_column(
        "bud_documents",
        sa.Column("impacted_repos", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # BUDCommit: add author tracking
    op.add_column("bud_commits", sa.Column("author_name", sa.String(length=255), nullable=True))
    op.add_column("bud_commits", sa.Column("author_email", sa.String(length=255), nullable=True))
    op.add_column("bud_commits", sa.Column("user_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_bud_commit_user_id", "bud_commits", "users", ["user_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_bud_commit_user_id", "bud_commits", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_bud_commit_user_id", table_name="bud_commits")
    op.drop_constraint("fk_bud_commit_user_id", "bud_commits", type_="foreignkey")
    op.drop_column("bud_commits", "user_id")
    op.drop_column("bud_commits", "author_email")
    op.drop_column("bud_commits", "author_name")
    op.drop_column("bud_documents", "impacted_repos")
