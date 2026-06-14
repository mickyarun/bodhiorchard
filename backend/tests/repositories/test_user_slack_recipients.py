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

"""Structural test for ``UserRepository.list_slack_recipients``.

This is the single chokepoint every category-scoped Slack notification flows
through, so the opt-out filter must compile to the right predicate. The
codebase avoids real-DB fixtures (see ``tests/conftest.py``); we capture the
SELECT and assert on its compiled SQL shape.

The load-bearing rule: a member is excluded ONLY when the resolved value is
``'false'``. The predicate is ``COALESCE(notification_prefs ->> category,
<default>) <> 'false'``, where ``<default>`` is the registry's
``default_enabled`` for the category. For an opt-out category the default is
``'true'`` so a missing key (the common case — most members never open
settings) resolves to *kept*; for an opt-in category the default is ``'false'``
so a missing key resolves to *dropped*. A naive ``->> = 'true'`` would silently
drop everyone who never set a preference on an opt-out category.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.repositories.user import UserRepository
from app.services.notifications import NotificationCategory


async def _capture_sql(category: str, *, default_enabled: bool = True) -> str:
    captured: dict[str, Any] = {}

    async def _execute(stmt: Any) -> MagicMock:
        captured["stmt"] = stmt
        result = MagicMock()
        result.all.return_value = []
        return result

    db = MagicMock(execute=AsyncMock(side_effect=_execute))
    await UserRepository(db).list_slack_recipients(
        uuid.uuid4(), category=category, default_enabled=default_enabled
    )
    return str(
        captured["stmt"].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


@pytest.mark.asyncio
async def test_opt_out_category_keeps_members_with_no_preference() -> None:
    sql = (await _capture_sql(NotificationCategory.MINIGAMES.value, default_enabled=True)).lower()
    # Active, slack-linked members of the org only.
    assert "join org_to_user" in sql
    assert "users.is_active" in sql
    assert "slack_id is not null" in sql
    # The predicate: COALESCE(->> category, 'true') <> 'false' — a missing key
    # coalesces to 'true' and survives, so opt-out members are kept by default.
    assert "coalesce((users.notification_prefs ->> 'minigames'), 'true') != 'false'" in sql


@pytest.mark.asyncio
async def test_opt_in_category_drops_members_with_no_preference() -> None:
    # default_enabled=False flips the COALESCE default to 'false', so a missing
    # key resolves to dropped — only members who explicitly enabled it are kept.
    sql = (await _capture_sql(NotificationCategory.QUIZ.value, default_enabled=False)).lower()
    assert "coalesce((users.notification_prefs ->> 'quiz'), 'false') != 'false'" in sql


@pytest.mark.asyncio
async def test_filter_binds_the_requested_category_key() -> None:
    sql = (await _capture_sql(NotificationCategory.QUIZ.value)).lower()
    assert "notification_prefs ->> 'quiz'" in sql
    assert "'minigames'" not in sql
