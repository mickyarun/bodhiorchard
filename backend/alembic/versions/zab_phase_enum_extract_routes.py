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

"""Add ``extract_routes`` and ``backend_link`` to the ``scan_phase`` enum.

Postgres enums are sticky — adding values requires ``ALTER TYPE``. The
``IF NOT EXISTS`` guard makes this re-run-safe so a partial state from
a prior failed migration doesn't block the upgrade. Mirrors the pattern
in ``zw_rename_phase_enum.py``.

Note: ``backend_link`` was previously used as a stage-name string in
``phase_routing.STAGE_TO_PHASE`` mapped to ``ScanPhase.FEATURE_SYNTHESIS``
— it never lived in the enum. Adding it now makes the global phase its
own first-class chip.

Revision ID: zab_phase_enum_extract_routes
Revises: zaa_backend_route_cache
Create Date: 2026-05-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "zab_phase_enum_extract_routes"
down_revision: str | None = "zaa_backend_route_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Append the two new enum values. Idempotent via IF NOT EXISTS."""
    op.execute("ALTER TYPE scan_phase ADD VALUE IF NOT EXISTS 'extract_routes'")
    op.execute("ALTER TYPE scan_phase ADD VALUE IF NOT EXISTS 'backend_link'")


def downgrade() -> None:
    """No-op — Postgres has no ``DROP VALUE`` for enums.

    Removing an enum value would require recreating the type and casting
    every column reference, which is more risk than the rollback path
    is worth. Leaving the values in place is harmless because no rows
    use them after a downgrade reverts the writers.
    """
