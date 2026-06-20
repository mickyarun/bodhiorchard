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

"""Tests for the bug-status QA SP rules (production-closed / rejected)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.bug import BugStatus, BugType
from app.services.sp_qa import award_qa_sp_on_bug_status


def _bug(bug_type: BugType) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), reporter_id=uuid.uuid4(), org_id=uuid.uuid4(), bug_type=bug_type
    )


@pytest.mark.asyncio
async def test_production_closed_rewards_qa_reporter() -> None:
    bug = _bug(BugType.PRODUCTION)
    with (
        patch("app.services.sp_qa.get_user_role", new=AsyncMock(return_value="qa")),
        patch("app.services.sp_qa.award_sp", new=AsyncMock(return_value=0.5)) as award,
        patch("app.services.sp_qa.penalize_sp", new=AsyncMock()) as pen,
    ):
        await award_qa_sp_on_bug_status(MagicMock(), bug, BugStatus.CLOSED)
    award.assert_awaited_once()
    assert award.await_args.kwargs["amount"] == 0.5
    assert award.await_args.kwargs["source_ref"] == f"sp_qa_prod:{bug.id}"
    pen.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejected_penalizes_qa_reporter() -> None:
    bug = _bug(BugType.TESTING)
    with (
        patch("app.services.sp_qa.get_user_role", new=AsyncMock(return_value="qa")),
        patch("app.services.sp_qa.award_sp", new=AsyncMock()) as award,
        patch("app.services.sp_qa.penalize_sp", new=AsyncMock(return_value=0.0)) as pen,
    ):
        await award_qa_sp_on_bug_status(MagicMock(), bug, BugStatus.REJECTED)
    pen.assert_awaited_once()
    assert pen.await_args.kwargs["amount"] == 0.10
    assert pen.await_args.kwargs["source_ref"] == f"sp_qa_rejected:{bug.id}"
    award.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_qa_reporter_gets_nothing() -> None:
    bug = _bug(BugType.PRODUCTION)
    with (
        patch("app.services.sp_qa.get_user_role", new=AsyncMock(return_value="developer")),
        patch("app.services.sp_qa.award_sp", new=AsyncMock()) as award,
        patch("app.services.sp_qa.penalize_sp", new=AsyncMock()) as pen,
    ):
        await award_qa_sp_on_bug_status(MagicMock(), bug, BugStatus.CLOSED)
    award.assert_not_awaited()
    pen.assert_not_awaited()


@pytest.mark.asyncio
async def test_testing_bug_closed_is_not_a_production_reward() -> None:
    bug = _bug(BugType.TESTING)
    with (
        patch("app.services.sp_qa.get_user_role", new=AsyncMock(return_value="qa")),
        patch("app.services.sp_qa.award_sp", new=AsyncMock()) as award,
        patch("app.services.sp_qa.penalize_sp", new=AsyncMock()) as pen,
    ):
        await award_qa_sp_on_bug_status(MagicMock(), bug, BugStatus.CLOSED)
    award.assert_not_awaited()
    pen.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_terminal_status_is_noop() -> None:
    bug = _bug(BugType.PRODUCTION)
    with patch("app.services.sp_qa.get_user_role", new=AsyncMock()) as role:
        await award_qa_sp_on_bug_status(MagicMock(), bug, BugStatus.IN_PROGRESS)
    role.assert_not_awaited()
