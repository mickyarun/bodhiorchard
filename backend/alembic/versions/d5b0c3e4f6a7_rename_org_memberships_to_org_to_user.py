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

"""rename org_memberships to org_to_user

Revision ID: d5b0c3e4f6a7
Revises: c4a9b2d3e5f6
Create Date: 2026-03-17 11:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5b0c3e4f6a7"
down_revision: str | None = "c4a9b2d3e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename org_memberships table and its indexes/constraints."""
    op.rename_table("org_memberships", "org_to_user")
    op.drop_constraint("uq_org_memberships_user_org", "org_to_user", type_="unique")
    op.create_unique_constraint("uq_org_to_user_user_org", "org_to_user", ["user_id", "org_id"])
    op.drop_index("ix_org_memberships_org_id", table_name="org_to_user")
    op.create_index("ix_org_to_user_org_id", "org_to_user", ["org_id"])
    op.drop_index("ix_org_memberships_user_id", table_name="org_to_user")
    op.create_index("ix_org_to_user_user_id", "org_to_user", ["user_id"])


def downgrade() -> None:
    """Revert table rename back to org_memberships."""
    op.drop_index("ix_org_to_user_user_id", table_name="org_to_user")
    op.create_index("ix_org_memberships_user_id", "org_to_user", ["user_id"])
    op.drop_index("ix_org_to_user_org_id", table_name="org_to_user")
    op.create_index("ix_org_memberships_org_id", "org_to_user", ["org_id"])
    op.drop_constraint("uq_org_to_user_user_org", "org_to_user", type_="unique")
    op.create_unique_constraint(
        "uq_org_memberships_user_org", "org_to_user", ["user_id", "org_id"]
    )
    op.rename_table("org_to_user", "org_memberships")
