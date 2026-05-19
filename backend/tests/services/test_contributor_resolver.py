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

"""Tests for ``contributor_resolver.get_bud_contributors``.

The stage-award split policy ("everyone who touched the BUD gets a slice")
is enforced by unioning two repository lookups. The test pins:
1. The union semantics — both sources contribute, duplicates de-dupe.
2. The empty-input short-circuit — no contributors → empty set, not error.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.contributor_resolver import get_bud_contributors


@pytest.mark.asyncio
async def test_unions_dev_activity_and_pr_authors() -> None:
    """Contributors = (dev_activity user_ids) ∪ (PR author user_ids)."""
    activity_user = uuid.uuid4()
    pr_user = uuid.uuid4()

    with (
        patch("app.services.contributor_resolver.DevActivityLogRepository") as mock_dev,
        patch("app.services.contributor_resolver.PullRequestRepository") as mock_pr,
    ):
        mock_dev.return_value.get_distinct_user_ids_for_bud = AsyncMock(
            return_value={activity_user}
        )
        mock_pr.return_value.get_distinct_author_user_ids_for_bud = AsyncMock(
            return_value={pr_user}
        )

        result = await get_bud_contributors(AsyncMock(), uuid.uuid4(), uuid.uuid4())

    assert result == {activity_user, pr_user}


@pytest.mark.asyncio
async def test_dedupes_users_appearing_in_both_sources() -> None:
    """A user with both commits and PRs counts once."""
    overlap_user = uuid.uuid4()

    with (
        patch("app.services.contributor_resolver.DevActivityLogRepository") as mock_dev,
        patch("app.services.contributor_resolver.PullRequestRepository") as mock_pr,
    ):
        mock_dev.return_value.get_distinct_user_ids_for_bud = AsyncMock(
            return_value={overlap_user}
        )
        mock_pr.return_value.get_distinct_author_user_ids_for_bud = AsyncMock(
            return_value={overlap_user}
        )

        result = await get_bud_contributors(AsyncMock(), uuid.uuid4(), uuid.uuid4())

    assert result == {overlap_user}


@pytest.mark.asyncio
async def test_empty_sources_return_empty_set() -> None:
    """No commits and no PRs → empty contributor set, not None or error."""
    with (
        patch("app.services.contributor_resolver.DevActivityLogRepository") as mock_dev,
        patch("app.services.contributor_resolver.PullRequestRepository") as mock_pr,
    ):
        mock_dev.return_value.get_distinct_user_ids_for_bud = AsyncMock(return_value=set())
        mock_pr.return_value.get_distinct_author_user_ids_for_bud = AsyncMock(return_value=set())

        result = await get_bud_contributors(AsyncMock(), uuid.uuid4(), uuid.uuid4())

    assert result == set()
