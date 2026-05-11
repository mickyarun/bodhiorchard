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

"""drop created_by from knowledge_items

Revision ID: 16f29f1b2a33
Revises: 5e3c255c0cdc
Create Date: 2026-03-25 20:24:54.188503

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "16f29f1b2a33"
down_revision: str | None = "5e3c255c0cdc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("knowledge_items", "created_by")


def downgrade() -> None:
    op.add_column(
        "knowledge_items",
        sa.Column("created_by", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(None, "knowledge_items", "users", ["created_by"], ["id"])
