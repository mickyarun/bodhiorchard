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

"""tracked_repositories: add setup_last_error (DEBUG)

Revision ID: zal_tracked_repos_setup_err
Revises: zak_org_github_app_slug
Create Date: 2026-05-07

DEBUG: surfaces ``commit_and_push_setup_worktree`` stderr to the frontend
chip tooltip so prod operators can see why a row is stuck in "Setup pending"
without grepping backend logs. Cleared on the next successful push.

This column (and the surrounding plumbing) is intentionally short-lived —
remove it once the setup-PR push path is reliably working in prod.

Revision ID kept ≤32 chars so it fits ``alembic_version.version_num``;
``alembic revision --autogenerate`` gives 12-char hashes by default which
sidesteps this cap entirely — preferred over hand-named IDs.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zal_tracked_repos_setup_err"
down_revision: str | None = "zak_org_github_app_slug"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tracked_repositories",
        sa.Column("setup_last_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tracked_repositories", "setup_last_error")
