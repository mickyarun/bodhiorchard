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

"""Add last_heartbeat_at to bud_agent_tasks for runaway-task recovery.

Agent tasks that outlive the backend process — because Docker Desktop's
VM was suspended with the laptop, or the backend crashed without running
its shutdown hook — used to stay stuck in ``running`` indefinitely. The
startup sweeper (``recover_stuck_agent_tasks``) only helps if the
backend actually restarts; a suspended-then-resumed container never
restarts.

``last_heartbeat_at`` is updated every ~30 s by the agent runner while
it's active, and a background sweeper marks tasks with stale heartbeats
as failed. The partial index keeps the sweeper's scan tight
(``running`` tasks only — usually < 10 at any time).

Revision ID: zk_agent_task_hb
Revises: zj_settings_perms
Create Date: 2026-04-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zk_agent_task_hb"
down_revision: str | None = "zj_settings_perms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bud_agent_tasks",
        sa.Column(
            "last_heartbeat_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_bud_agent_tasks_running_heartbeat",
        "bud_agent_tasks",
        ["last_heartbeat_at"],
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bud_agent_tasks_running_heartbeat",
        table_name="bud_agent_tasks",
    )
    op.drop_column("bud_agent_tasks", "last_heartbeat_at")
