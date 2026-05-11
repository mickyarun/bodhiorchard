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

"""merge_a1_and_z4_heads

Revision ID: 84cf56c5f2d8
Revises: a1_add_tech_arch_and_manager, z4_add_code_review_and_commits
Create Date: 2026-03-23 19:38:34.820667

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "84cf56c5f2d8"
down_revision: str | None = ("a1_add_tech_arch_and_manager", "z4_add_code_review_and_commits")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
