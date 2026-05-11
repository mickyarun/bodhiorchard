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

"""Statement-shape tests for ``SkillProfileRepository.list_with_users``.

The Skills UI and the ``get_team_context`` MCP tool both call this method
to render developer-skill-as-feature views. Phase E seeds rows with
``feature_id`` NULL (top-level directory like ``src``/``kube``); only
Phase E2 sets a real feature UUID after synthesis. If the NULL rows
leak into the response, the UI shows fake "skills" like ``src`` next to
real features. This test pins the read-side filter so an accidental
removal of the WHERE clause fails CI.

We use the same AsyncMock pattern as the rest of the suite — no
real DB — and inspect the compiled SQL of the statement passed to
``session.execute``.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.skill_profile import SkillProfileRepository


@pytest.mark.asyncio
async def test_list_with_users_filters_unmapped_feature_id() -> None:
    """``list_with_users`` must restrict to ``feature_id IS NOT NULL``.

    The Skills page and the team-context MCP tool depend on this
    filter; without it, Phase E's directory-named seeds (``src``,
    ``kube``) leak in alongside real synthesised features.
    """
    db = MagicMock()
    # ``await session.execute(...)`` returns a Result whose ``.all()`` is
    # synchronous — model that with an AsyncMock wrapping a plain Mock.
    result_obj = MagicMock()
    result_obj.all.return_value = []
    execute_mock = AsyncMock(return_value=result_obj)
    db.execute = execute_mock

    repo = SkillProfileRepository(db, org_id=uuid.uuid4())
    await repo.list_with_users()

    assert execute_mock.await_count == 1
    stmt = execute_mock.await_args.args[0]
    rendered = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    # Both org scoping and the feature_id guard must be present.
    assert "feature_id IS NOT NULL" in rendered
    assert "skill_profiles.org_id" in rendered
