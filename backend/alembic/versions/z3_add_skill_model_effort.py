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

"""Add model and effort columns to agent_skill_overrides.

Revision ID: z3_add_skill_model_effort
Revises: z2_add_design_path
Create Date: 2026-03-23 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "z3_add_skill_model_effort"
down_revision: str = "z2_add_design_path"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add model and effort columns to agent_skill_overrides."""
    op.add_column(
        "agent_skill_overrides",
        sa.Column("model", sa.String(100), nullable=False, server_default=""),
    )
    op.add_column(
        "agent_skill_overrides",
        sa.Column("effort", sa.String(20), nullable=False, server_default=""),
    )


def downgrade() -> None:
    """Remove model and effort columns from agent_skill_overrides."""
    op.drop_column("agent_skill_overrides", "effort")
    op.drop_column("agent_skill_overrides", "model")
