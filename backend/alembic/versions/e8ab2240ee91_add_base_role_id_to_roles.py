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

"""Add ``base_role_id`` FK to ``roles`` for custom-role inheritance.

The phase auto-assigner needs to resolve every membership to one of
the seeded ``UserRole`` values. Custom roles created via POST /v1/roles
declare their inheritance via this self-referential FK; ``Role.scope_type``
discriminates SYSTEM vs CUSTOM rows in the query
(``UserRepository.list_active_with_role``).

Column is nullable at the DB level — SYSTEM rows leave it ``NULL``,
CUSTOM rows always set it. The invariant is enforced by the Pydantic
schema (``RoleCreate.base_role_id`` is required) and the API handler
(``_validate_base_role`` only accepts active system roles), not by a
CHECK constraint.

Revision ID: e8ab2240ee91
Revises: 281bc0331ae5
Create Date: 2026-05-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8ab2240ee91"
down_revision: str | None = "281bc0331ae5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable self-FK + supporting index."""
    op.add_column("roles", sa.Column("base_role_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_roles_base_role_id"), "roles", ["base_role_id"], unique=False)
    op.create_foreign_key(
        "fk_roles_base_role_id_roles",
        "roles",
        "roles",
        ["base_role_id"],
        ["id"],
    )


def downgrade() -> None:
    """Reverse the upgrade."""
    op.drop_constraint("fk_roles_base_role_id_roles", "roles", type_="foreignkey")
    op.drop_index(op.f("ix_roles_base_role_id"), table_name="roles")
    op.drop_column("roles", "base_role_id")
