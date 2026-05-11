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

"""Add repo_layer / tech_stack / db_flavor to tracked_repositories.

Populated by the new ``classify_repo`` per-repo stage which runs after
``ingest`` and inspects the worktree's manifest files (see
``app/services/scan/repo_classify``). The downstream ``backend_link``
stage reads ``repo_layer`` to decide which repos to index as backends
vs treat as frontends whose features need linking.

Columns are nullable — existing rows are left unclassified until the
next scan touches them. The ``repo_layer`` Postgres enum is created
alongside the column.

Revision ID: zx_repo_layer
Revises: zw_rename_phase_enum
Create Date: 2026-05-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zx_repo_layer"
down_revision: str | None = "zw_rename_phase_enum"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_REPO_LAYER_VALUES = ("frontend", "backend", "processor", "batch", "db", "shared")


def upgrade() -> None:
    """Create the ``repo_layer`` Postgres enum and add the three columns.

    Uses ``create_type=False`` on the column add and emits the CREATE
    TYPE separately so the enum can be reused (e.g. by future tables
    or partial backfills) without alembic complaining about
    duplicate-type creation in subsequent migrations.
    """
    repo_layer_enum = sa.Enum(*_REPO_LAYER_VALUES, name="repo_layer")
    repo_layer_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "tracked_repositories",
        sa.Column(
            "repo_layer",
            sa.Enum(*_REPO_LAYER_VALUES, name="repo_layer", create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        "tracked_repositories",
        sa.Column("tech_stack", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "tracked_repositories",
        sa.Column("db_flavor", sa.String(length=50), nullable=True),
    )
    op.create_index(
        "ix_tracked_repositories_repo_layer",
        "tracked_repositories",
        ["repo_layer"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tracked_repositories_repo_layer",
        table_name="tracked_repositories",
    )
    op.drop_column("tracked_repositories", "db_flavor")
    op.drop_column("tracked_repositories", "tech_stack")
    op.drop_column("tracked_repositories", "repo_layer")
    sa.Enum(name="repo_layer").drop(op.get_bind(), checkfirst=True)
