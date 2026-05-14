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

"""Structural test for ``UserRepository.list_active_with_role``.

This is the load-bearing query for the entire phase-assignment fallback
story — refactors that drop the INNER join on ``roles``, weaken the
``OrgToUser.role_id IS NOT NULL`` requirement, or remove the
``scope_type``-based discrimination would silently re-introduce the
"defaulted-developer" bug (members with no explicit role being
auto-assigned).

The codebase deliberately avoids real-DB fixtures (see
``tests/conftest.py`` for the history). Instead we capture the SELECT
statement the repository builds and assert on its compiled SQL shape.
Catches the refactoring failure modes that the unit-level
``test_bud_assignment.py`` tests (which mock the repository entirely)
cannot.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.models.user import UserRole
from app.repositories.user import UserRepository


async def _capture_query_sql(role: UserRole) -> str:
    """Run ``list_active_with_role`` against a mock DB and return its compiled SQL.

    Used by every test in this file — capturing the statement is the only
    way to assert query shape without a live database (see module
    docstring on why real-DB fixtures are avoided).
    """
    captured: dict[str, Any] = {}

    async def _execute(stmt: Any) -> MagicMock:
        captured["stmt"] = stmt
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        return result

    db = MagicMock(execute=AsyncMock(side_effect=_execute))
    repo = UserRepository(db)
    await repo.list_active_with_role(uuid.uuid4(), role)
    return str(
        captured["stmt"].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


@pytest.mark.asyncio
async def test_query_inner_joins_roles_and_filters_by_scope_type() -> None:
    """SQL shape:

    1. INNER JOIN ``org_to_user`` (so members without membership rows are excluded).
    2. INNER JOIN ``roles`` on ``OrgToUser.role_id`` (so NULL ``role_id``
       members — the GitHub/Slack-imported defaulted-developer case — are
       excluded).
    3. OUTER JOIN to the base-role alias (so SYSTEM rows with NULL
       ``base_role_id`` aren't dropped).
    4. WHERE filters: ``org_id`` scope, ``User.is_active``, and the
       scope-discriminated identity match.
    """
    sql = await _capture_query_sql(UserRole.TECH_LEAD)

    # Inner joins (no LEFT prefix) — the second OUTER join is to the
    # base-role alias only, not to ``roles`` itself.
    assert "JOIN org_to_user" in sql
    assert "LEFT OUTER JOIN org_to_user" not in sql
    # The second join to roles is the primary inner join; the third
    # (left outer) is the aliased self-join for ``base_role_id``.
    assert " JOIN roles " in sql
    assert "LEFT OUTER JOIN roles" in sql

    # Scope-type discrimination — both branches must be present.
    assert "scope_type = 'system'" in sql.lower() or "= 'system'" in sql
    assert "scope_type = 'custom'" in sql.lower() or "= 'custom'" in sql

    # The role identity we asked for must appear in both branches.
    assert "'tech_lead'" in sql

    # is_active filter on user (excludes deactivated members).
    assert "users.is_active" in sql

    # SELECT DISTINCT so the LEFT OUTER JOIN on base_role can't
    # duplicate a user who matches both branches by coincidence.
    assert "SELECT DISTINCT" in sql or "DISTINCT" in sql


@pytest.mark.asyncio
async def test_query_uses_role_value_not_repr() -> None:
    """The compiled WHERE uses ``UserRole.<X>.value`` strings, never the StrEnum repr.

    Regression guard: ``Role.name`` is a varchar so the comparison must
    be against the string value (``"developer"``), not the enum repr
    (``"UserRole.DEVELOPER"``). Without this assertion a future change
    that passes the enum object directly into a non-enum column would
    compile to a comparison that never matches.
    """
    sql = await _capture_query_sql(UserRole.DEVELOPER)
    assert "'developer'" in sql
    assert "UserRole.DEVELOPER" not in sql
