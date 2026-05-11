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

"""Add role_id to org_to_user for per-org RBAC roles.

Revision ID: m1_multi_org_prepare
Revises: z7_drop_skill_profile_repo
Create Date: 2026-03-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "m1_multi_org_prepare"
down_revision: str | None = "z7_drop_skill_profile_repo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add role_id FK column to org_to_user."""
    op.add_column(
        "org_to_user",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_org_to_user_role_id",
        "org_to_user",
        "roles",
        ["role_id"],
        ["id"],
    )


def downgrade() -> None:
    """Remove role_id from org_to_user."""
    op.drop_constraint("fk_org_to_user_role_id", "org_to_user", type_="foreignkey")
    op.drop_column("org_to_user", "role_id")
