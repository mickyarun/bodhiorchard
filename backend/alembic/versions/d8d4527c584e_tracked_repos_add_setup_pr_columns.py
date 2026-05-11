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

"""tracked_repos: add setup_pr columns

Revision ID: d8d4527c584e
Revises: zq_drop_meta_communities
Create Date: 2026-04-27 13:03:42.898450

Adds Bodhiorchard MCP setup-PR tracking columns to ``tracked_repositories``:
- ``setup_branch_pushed_at``: last successful push of ``bodhiorchard/init-setup``.
- ``setup_pr_url`` / ``setup_pr_number`` / ``setup_pr_state``: identity and
  lifecycle of the auto-opened (or adopted) GitHub PR.

The dedicated ``tracked_repo_setup_pr_state`` enum is dropped on downgrade
so the type doesn't linger in the DB after a rollback.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8d4527c584e"
down_revision: str | None = "zq_drop_meta_communities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SETUP_PR_STATE_ENUM = sa.Enum(
    "open",
    "merged",
    "closed",
    name="tracked_repo_setup_pr_state",
)


def upgrade() -> None:
    SETUP_PR_STATE_ENUM.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "tracked_repositories",
        sa.Column("setup_branch_pushed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tracked_repositories",
        sa.Column("setup_pr_url", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "tracked_repositories",
        sa.Column("setup_pr_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tracked_repositories",
        sa.Column(
            "setup_pr_state",
            SETUP_PR_STATE_ENUM,
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("tracked_repositories", "setup_pr_state")
    op.drop_column("tracked_repositories", "setup_pr_number")
    op.drop_column("tracked_repositories", "setup_pr_url")
    op.drop_column("tracked_repositories", "setup_branch_pushed_at")
    SETUP_PR_STATE_ENUM.drop(op.get_bind(), checkfirst=True)
