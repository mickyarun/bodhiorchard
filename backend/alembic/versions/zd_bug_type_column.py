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

"""Add bug_type column to bugs table.

Classifies bugs as 'testing' (found during QA) or 'production' (found
after release). Auto-set based on BUD status at bug creation time.

Revision ID: zd_bug_type_column
Revises: zc_triage_session_type
Create Date: 2026-04-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zd_bug_type_column"
down_revision: str | None = "3922c4bb35ad"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add bug_type enum + column with default 'testing', and composite index."""
    bug_type_enum = sa.Enum("testing", "production", name="bug_type")
    bug_type_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "bugs",
        sa.Column(
            "bug_type",
            bug_type_enum,
            nullable=False,
            server_default="testing",
        ),
    )
    op.create_index(
        "ix_bugs_bud_id_status",
        "bugs",
        ["bud_id", "status"],
    )


def downgrade() -> None:
    """Drop index, bug_type column, and enum."""
    op.drop_index("ix_bugs_bud_id_status", table_name="bugs")
    op.drop_column("bugs", "bug_type")
    sa.Enum(name="bug_type").drop(op.get_bind(), checkfirst=True)
