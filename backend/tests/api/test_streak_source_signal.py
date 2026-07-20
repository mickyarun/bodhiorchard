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

"""Telling a dead streak apart from a quiet one.

``check_and_award_streak`` has exactly one trigger: ``/mcp/dev-activity``, which
each developer's own Claude Code hook posts to. Where that hook isn't deployed
the streak stays at zero however much work ships, and the XP guide would go on
advertising it next to rules that do fire — reading as a broken counter rather
than a missing integration.

The signal is org-wide on purpose: one user with no events is simply someone who
hasn't coded today, while nobody in the org ever having reported means the hook
isn't wired up anywhere.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.dev_activity import DevActivityLogRepository


def _repo(first_row: object | None) -> DevActivityLogRepository:
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=first_row)
    db.execute = AsyncMock(return_value=result)
    return DevActivityLogRepository(db, org_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_no_events_anywhere_means_the_hook_is_not_deployed() -> None:
    assert await _repo(None).any_event_exists() is False


@pytest.mark.asyncio
async def test_a_single_event_is_enough_to_count_as_connected() -> None:
    """Self-healing: the moment any hook reports, streaks are live again — no
    setting to flip and nothing to keep in sync."""
    assert await _repo(uuid.uuid4()).any_event_exists() is True


@pytest.mark.asyncio
async def test_the_query_is_org_scoped() -> None:
    """Another tenant's activity must not make this org look connected."""
    repo = _repo(None)
    await repo.any_event_exists()

    sql = str(repo._db.execute.call_args.args[0]).lower()
    assert "org_id" in sql
    # Existence check only — never drag the whole table back for a boolean.
    assert "limit" in sql
