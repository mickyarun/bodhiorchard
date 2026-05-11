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

"""Add max_turns column to agent_skill_overrides.

Revision ID: y5f6a7b8c9
Revises: x4e5f6a7b8
Create Date: 2026-03-22 12:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "y5f6a7b8c9"
down_revision = "x4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_skill_overrides",
        sa.Column("max_turns", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("agent_skill_overrides", "max_turns")
