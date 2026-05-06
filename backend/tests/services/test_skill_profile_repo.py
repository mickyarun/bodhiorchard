# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

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
