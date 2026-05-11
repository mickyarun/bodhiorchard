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

"""Add session_type to triage_sessions for bug vs BUD triage.

Revision ID: zc_triage_session_type
Revises: zb_bud_release_tracking
Create Date: 2026-04-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zc_triage_session_type"
down_revision: str | None = "zb_bud_release_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add session_type column with default 'bud'."""
    op.add_column(
        "triage_sessions",
        sa.Column(
            "session_type",
            sa.String(length=10),
            nullable=False,
            server_default="bud",
        ),
    )


def downgrade() -> None:
    """Drop session_type column."""
    op.drop_column("triage_sessions", "session_type")
