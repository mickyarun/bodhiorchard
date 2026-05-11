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

"""merge zb_drop_actor_role + zc_triage_session_type

Revision ID: 18bb5e095ca2
Revises: zb_drop_actor_role_column, zc_triage_session_type
Create Date: 2026-04-12 19:49:28.443489

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "18bb5e095ca2"
down_revision: str | None = ("zb_drop_actor_role_column", "zc_triage_session_type")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
