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

"""skill_points Integer to Numeric(10,2) for fractional SP economy

Revision ID: ze_sp_numeric
Revises: 3922c4bb35ad
Create Date: 2026-04-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ze_sp_numeric"
down_revision: str | None = "3922c4bb35ad"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Convert skill_points from Integer to Numeric(10,2) for fractional SP.
    # Reset all values to 0 — old 1:1 SP economy is replaced by role-based awards.
    op.alter_column(
        "developer_xp",
        "skill_points",
        type_=sa.Numeric(10, 2),
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default="0",
        server_default="0",
    )
    op.execute("UPDATE developer_xp SET skill_points = 0")


def downgrade() -> None:
    op.alter_column(
        "developer_xp",
        "skill_points",
        type_=sa.Integer(),
        existing_type=sa.Numeric(10, 2),
        existing_nullable=False,
        existing_server_default="0",
        server_default="0",
        postgresql_using="skill_points::integer",
    )
