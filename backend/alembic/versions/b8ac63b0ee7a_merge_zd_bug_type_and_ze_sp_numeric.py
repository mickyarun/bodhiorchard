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

"""merge zd_bug_type and ze_sp_numeric

Revision ID: b8ac63b0ee7a
Revises: zd_bug_type_column, ze_sp_numeric
Create Date: 2026-04-12 23:40:54.134987

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "b8ac63b0ee7a"
down_revision: str | None = ("zd_bug_type_column", "ze_sp_numeric")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
