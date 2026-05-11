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

"""Add RESTRICT ondelete to bud_agent_tasks.skill_id FK.

The z8 migration created the FK without an ondelete action.
This adds RESTRICT to prevent accidental skill deletion while
agent tasks reference it.

Revision ID: z9_add_restrict_to_skill_fk
Revises: z8_agent_skills_refactor
Create Date: 2026-03-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "z9_add_restrict_to_skill_fk"
down_revision: str | None = "z8_agent_skills_refactor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Replace skill_id FK with RESTRICT ondelete."""
    op.drop_constraint("bud_agent_tasks_skill_id_fkey", "bud_agent_tasks", type_="foreignkey")
    op.create_foreign_key(
        "bud_agent_tasks_skill_id_fkey",
        "bud_agent_tasks",
        "agent_skills",
        ["skill_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Revert to FK without ondelete."""
    op.drop_constraint("bud_agent_tasks_skill_id_fkey", "bud_agent_tasks", type_="foreignkey")
    op.create_foreign_key(
        "bud_agent_tasks_skill_id_fkey",
        "bud_agent_tasks",
        "agent_skills",
        ["skill_id"],
        ["id"],
    )
