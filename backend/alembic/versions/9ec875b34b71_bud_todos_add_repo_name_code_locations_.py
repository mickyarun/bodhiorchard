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

"""Add repo_name, code_locations, description to bud_todos.

Promotes three pieces of TODO data to first-class columns so the
Development board can render a structured Notion-style table:

  - ``repo_name``: the repo a TODO targets (previously trapped in a
    leading ``[RepoName]`` prefix on ``title``).
  - ``code_locations``: file paths the TODO touches (previously buried
    inline in prose).
  - ``description``: 1-3 sentence scannable intent surfaced next to the
    title; ``context_md`` retains long-form spec.

``description`` and ``repo_name`` are nullable — the agent legitimately
omits them for cross-cutting / unstructured tasks. ``code_locations`` is
NOT NULL with a default of ``'[]'::jsonb`` because "no paths" is always
representable as an empty array; null would force every consumer to
re-check.

Revision ID: 9ec875b34b71
Revises: x1a2b3c4d5e6
Create Date: 2026-05-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "9ec875b34b71"
down_revision: str | None = "x1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bud_todos",
        sa.Column("description", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "bud_todos",
        sa.Column("repo_name", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "bud_todos",
        sa.Column(
            "code_locations",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("bud_todos", "code_locations")
    op.drop_column("bud_todos", "repo_name")
    op.drop_column("bud_todos", "description")
