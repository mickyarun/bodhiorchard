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

"""Unit tests for :mod:`app.services.bud_chat_cancel`.

Covers the three branches:
1. No active chat → returns None (handler turns into 404).
2. Active + alive in ``_job_store`` → signals cancel; worker's terminal
   hook clears the pointer (asserted indirectly via no in-service commit).
3. Active but stale pointer → clears the pointer directly + commits.
Plus signal failure → ``BUDChatCancelError`` (no DB writes).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.bud_section_session import ChatActiveJobStatus
from app.repositories.bud_section_session import ActiveJobPointer
from app.services.bud_chat_cancel import BUDChatCancelError, cancel_chat


def _make_pointer(job_id: str = "job-123") -> ActiveJobPointer:
    return ActiveJobPointer(
        job_id=job_id,
        status=ChatActiveJobStatus.RUNNING,
        started_at=datetime(2026, 5, 15, 12, 0, 0, tzinfo=UTC),
    )


def _patch_repo(pointer: ActiveJobPointer | None) -> tuple[MagicMock, MagicMock]:
    repo = MagicMock()
    repo.get_active_job_pointer = AsyncMock(return_value=pointer)
    repo.clear_active_job = AsyncMock(return_value=None)
    repo_ctx = patch(
        "app.services.bud_chat_cancel.BUDSectionSessionRepository",
        return_value=repo,
    )
    return repo, repo_ctx


@pytest.mark.asyncio
async def test_returns_none_when_no_active_chat() -> None:
    """No durable pointer → service returns None, no DB writes."""
    db = MagicMock()
    db.commit = AsyncMock()
    repo, repo_ctx = _patch_repo(None)
    with repo_ctx:
        out = await cancel_chat(
            db,
            org_id=uuid.uuid4(),
            bud_id=uuid.uuid4(),
            section="requirements_md",
            design_id=None,
            reason="user",
        )
    assert out is None
    repo.clear_active_job.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_alive_signals_cancel_and_defers_cleanup_to_worker() -> None:
    """Live job → ``cancel_in_memory_job`` called; service does NOT commit.

    The worker's ``finally`` hook in ``handle_chat_job`` is responsible
    for clearing the pointer on the alive path.
    """
    db = MagicMock()
    db.commit = AsyncMock()
    repo, repo_ctx = _patch_repo(_make_pointer())
    with (
        repo_ctx,
        patch("app.services.bud_chat_cancel.is_job_running", return_value=True),
        patch(
            "app.services.bud_chat_cancel.cancel_in_memory_job", return_value=True
        ) as cancel_signal,
    ):
        out = await cancel_chat(
            db,
            org_id=uuid.uuid4(),
            bud_id=uuid.uuid4(),
            section="requirements_md",
            design_id=None,
            reason="user",
        )
    assert out == "job-123"
    cancel_signal.assert_called_once_with("job-123", reason="user")
    # No direct DB writes on the alive path — worker owns the cleanup.
    repo.clear_active_job.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_stale_pointer_clears_directly_and_commits() -> None:
    """Pointer present but in-memory task gone → lazy clear + commit."""
    db = MagicMock()
    db.commit = AsyncMock()
    bud_id = uuid.uuid4()
    repo, repo_ctx = _patch_repo(_make_pointer("stale-job"))
    with (
        repo_ctx,
        patch("app.services.bud_chat_cancel.is_job_running", return_value=False),
        patch("app.services.bud_chat_cancel.cancel_in_memory_job") as cancel_signal,
    ):
        out = await cancel_chat(
            db,
            org_id=uuid.uuid4(),
            bud_id=bud_id,
            section="design",
            design_id=None,
            reason="user",
        )
    assert out == "stale-job"
    cancel_signal.assert_not_called()
    repo.clear_active_job.assert_awaited_once_with(bud_id, "design", None)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_signal_failure_raises_bud_chat_cancel_error() -> None:
    """``cancel_in_memory_job`` raising → ``BUDChatCancelError``, no commits."""
    db = MagicMock()
    db.commit = AsyncMock()
    repo, repo_ctx = _patch_repo(_make_pointer())
    boom = RuntimeError("can't kill subprocess")
    with (
        repo_ctx,
        patch("app.services.bud_chat_cancel.is_job_running", return_value=True),
        patch("app.services.bud_chat_cancel.cancel_in_memory_job", side_effect=boom),
        pytest.raises(BUDChatCancelError, match="can't kill subprocess"),
    ):
        await cancel_chat(
            db,
            org_id=uuid.uuid4(),
            bud_id=uuid.uuid4(),
            section="requirements_md",
            design_id=None,
            reason="user",
        )
    repo.clear_active_job.assert_not_called()
    db.commit.assert_not_called()
