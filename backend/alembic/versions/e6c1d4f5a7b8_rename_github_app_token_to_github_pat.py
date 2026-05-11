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

"""Rename github_app_token to github_pat on organizations.

Revision ID: e6c1d4f5a7b8
Revises: d5b0c3e4f6a7
Create Date: 2026-03-17 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6c1d4f5a7b8"
down_revision: str | None = "d5b0c3e4f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename github_app_token column to github_pat."""
    op.alter_column(
        "organizations",
        "github_app_token",
        new_column_name="github_pat",
    )


def downgrade() -> None:
    """Revert github_pat back to github_app_token."""
    op.alter_column(
        "organizations",
        "github_pat",
        new_column_name="github_app_token",
    )
