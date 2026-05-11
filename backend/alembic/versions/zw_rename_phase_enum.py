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

"""Rename gitnexus_index → code_index across stored phase / status values.

The ``ScanPhase`` enum and the ``Scan.aggregate_status`` varchar both
dropped their last "gitnexus" branding when bodhiorchard moved to
graphify. Two values changed:

* ``scan_phase`` Postgres ENUM: ``gitnexus_index``  →  ``code_index``
* ``scans.status`` (varchar): rows with ``setting_up_gitnexus``
                                →  ``setting_up_index``

For the enum we use Postgres 10+'s ``ALTER TYPE … RENAME VALUE`` which
is atomic in a transaction and leaves no orphan values behind. Alembic
autogenerate doesn't detect enum-value renames, so this is hand-written.

Revision ID: zw_rename_phase_enum
Revises: zv_cluster_cache_graphify
Create Date: 2026-04-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "zw_rename_phase_enum"
down_revision: str | None = "zv_cluster_cache_graphify"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE scan_phase RENAME VALUE 'gitnexus_index' TO 'code_index'")
    op.execute("UPDATE scans SET status = 'setting_up_index' WHERE status = 'setting_up_gitnexus'")


def downgrade() -> None:
    op.execute("UPDATE scans SET status = 'setting_up_gitnexus' WHERE status = 'setting_up_index'")
    op.execute("ALTER TYPE scan_phase RENAME VALUE 'code_index' TO 'gitnexus_index'")
