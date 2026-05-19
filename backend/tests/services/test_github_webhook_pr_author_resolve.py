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

"""Tests for ``github_webhook_handler._resolve_pr_author``.

XP/SP credit for PR-opened, PR-merged events depends on resolving the
GitHub PR author to a bodhi user. The primary lookup matches against
``users.github_username``; absence of that mapping (common in mock/test
setups) silently dropped every PR XP award before this fallback shipped.
The fallback credits the BUD assignee when the PR is on a BUD branch
and the BUD has one. These tests pin down the priority order so a
regression doesn't double-credit (assignee winning when username also
matches) or under-credit (skipping the fallback when username misses).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.github_webhook_handler import _resolve_pr_author


@pytest.mark.asyncio
async def test_username_match_wins_no_bud_lookup() -> None:
    """When github_username resolves, the BUD lookup must not run."""
    org_id = uuid.uuid4()
    bud_id = uuid.uuid4()
    user_id = uuid.uuid4()

    with (
        patch("app.services.github_webhook_handler.UserRepository") as mock_user_repo,
        patch("app.services.github_webhook_handler.BUDRepository") as mock_bud_repo,
    ):
        user_instance = mock_user_repo.return_value
        user_instance.get_id_by_github_login = AsyncMock(return_value=user_id)

        result_id, source = await _resolve_pr_author(MagicMock(), org_id, "mickyarun", bud_id)

    assert result_id == user_id
    assert source == "github_username"
    mock_bud_repo.assert_not_called()


@pytest.mark.asyncio
async def test_falls_back_to_bud_assignee_when_username_misses() -> None:
    """Username miss + BUD with assignee → assignee_id credited."""
    org_id = uuid.uuid4()
    bud_id = uuid.uuid4()
    assignee_id = uuid.uuid4()
    bud = MagicMock(assignee_id=assignee_id)

    with (
        patch("app.services.github_webhook_handler.UserRepository") as mock_user_repo,
        patch("app.services.github_webhook_handler.BUDRepository") as mock_bud_repo,
    ):
        mock_user_repo.return_value.get_id_by_github_login = AsyncMock(return_value=None)
        mock_bud_repo.return_value.get_by_id = AsyncMock(return_value=bud)

        result_id, source = await _resolve_pr_author(MagicMock(), org_id, "unknown_login", bud_id)

    assert result_id == assignee_id
    assert source == "bud_assignee"


@pytest.mark.asyncio
async def test_returns_unresolved_when_username_misses_and_no_bud() -> None:
    """Username miss + no bud_id → unresolved (don't credit anyone)."""
    with patch("app.services.github_webhook_handler.UserRepository") as mock_user_repo:
        mock_user_repo.return_value.get_id_by_github_login = AsyncMock(return_value=None)

        result_id, source = await _resolve_pr_author(MagicMock(), uuid.uuid4(), "nobody", None)

    assert result_id is None
    assert source == "unresolved"


@pytest.mark.asyncio
async def test_returns_unresolved_when_bud_has_no_assignee() -> None:
    """Username miss + BUD exists but has no assignee → unresolved."""
    bud = MagicMock(assignee_id=None)

    with (
        patch("app.services.github_webhook_handler.UserRepository") as mock_user_repo,
        patch("app.services.github_webhook_handler.BUDRepository") as mock_bud_repo,
    ):
        mock_user_repo.return_value.get_id_by_github_login = AsyncMock(return_value=None)
        mock_bud_repo.return_value.get_by_id = AsyncMock(return_value=bud)

        result_id, source = await _resolve_pr_author(
            MagicMock(), uuid.uuid4(), "nobody", uuid.uuid4()
        )

    assert result_id is None
    assert source == "unresolved"


@pytest.mark.asyncio
async def test_returns_unresolved_when_bud_id_dangles() -> None:
    """Username miss + bud_id passed but BUD row gone → unresolved."""
    with (
        patch("app.services.github_webhook_handler.UserRepository") as mock_user_repo,
        patch("app.services.github_webhook_handler.BUDRepository") as mock_bud_repo,
    ):
        mock_user_repo.return_value.get_id_by_github_login = AsyncMock(return_value=None)
        mock_bud_repo.return_value.get_by_id = AsyncMock(return_value=None)

        result_id, source = await _resolve_pr_author(
            MagicMock(), uuid.uuid4(), "nobody", uuid.uuid4()
        )

    assert result_id is None
    assert source == "unresolved"
