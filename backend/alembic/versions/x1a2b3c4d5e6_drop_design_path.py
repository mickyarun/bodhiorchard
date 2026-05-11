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

"""Drop design_path from bud_designs.

Wireframe HTML is now persisted exclusively via the ``write_bud_design`` MCP
tool — the agent no longer writes wireframes to disk and the file-path
column has no consumer. This retirement reverses the temporary re-add in
``z2_add_design_path`` (2026-03-22), which itself had reverted the original
drop in ``v2e3f4g5h6_simplify_bud_schema`` (2026-03-21).

Revision ID: x1a2b3c4d5e6
Revises: ed5143cd2646
Create Date: 2026-05-11 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "x1a2b3c4d5e6"
down_revision: str = "ed5143cd2646"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop design_path column from bud_designs."""
    op.drop_column("bud_designs", "design_path")


def downgrade() -> None:
    """Restore design_path column on bud_designs (nullable)."""
    op.add_column(
        "bud_designs",
        sa.Column("design_path", sa.String(500), nullable=True),
    )
