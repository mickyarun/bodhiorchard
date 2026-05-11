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

"""Add user_id and session_id to bud_chat_messages for collaborative sessions.

Revision ID: w3f4g5h6i7
Revises: v2e3f4g5h6
Create Date: 2026-03-21 14:10:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "w3f4g5h6i7"
down_revision = "v2e3f4g5h6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bud_chat_messages",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "bud_chat_messages",
        sa.Column("session_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_bud_chat_session",
        "bud_chat_messages",
        ["bud_id", "session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_bud_chat_session", table_name="bud_chat_messages")
    op.drop_column("bud_chat_messages", "session_id")
    op.drop_column("bud_chat_messages", "user_id")
