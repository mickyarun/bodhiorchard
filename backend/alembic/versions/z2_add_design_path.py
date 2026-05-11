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

"""Add design_path column to bud_designs table.

Revision ID: z2_add_design_path
Revises: z1a2b3c4d5
Create Date: 2026-03-22 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "z2_add_design_path"
down_revision: str = "z1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add design_path column to bud_designs."""
    op.add_column(
        "bud_designs",
        sa.Column("design_path", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    """Remove design_path column from bud_designs."""
    op.drop_column("bud_designs", "design_path")
