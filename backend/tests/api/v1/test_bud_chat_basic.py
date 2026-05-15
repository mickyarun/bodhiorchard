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

"""Baseline behaviour tests for the BUD chat endpoint.

Covers the not-found short-circuit. The full HTTP+DB harness isn't
wired here (see ``tests/conftest.py``), so the tests call the endpoint
handler directly with the repositories and ``create_job`` stubbed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.bud_chat import BUDChatRequest, chat_bud, get_active_chat_job
from app.models.bud_section_session import ChatActiveJobStatus
from app.repositories.bud_section_session import ActiveJobPointer
from app.schemas.jobs import JobState, JobStatusRead
from tests.api.v1._bud_chat_helpers import make_user


@pytest.mark.asyncio
async def test_chat_bud_404_when_bud_missing() -> None:
    """Missing BUD → ``HTTPException(404)`` before any further work."""
    user = make_user()
    db = MagicMock()
    bud_repo = MagicMock()
    bud_repo.get_by_id = AsyncMock(return_value=None)

    with (
        patch("app.api.v1.bud_chat.BUDRepository", return_value=bud_repo),
        pytest.raises(HTTPException) as ei,
    ):
        await chat_bud(
            bud_id=uuid.uuid4(),
            body=BUDChatRequest(message="hi", section="requirements_md"),
            current_user=user,
            db=db,
        )
    assert ei.value.status_code == 404


# ── GET /chat/active-job ────────────────────────────────────────────


def _make_running_status(job_id: str | None = None) -> JobStatusRead:
    return JobStatusRead(
        job_id=job_id or str(uuid.uuid4()),
        job_type="bud_chat",
        state=JobState.RUNNING,
        status_message="Reading file...",
    )


def _make_pointer(job_id: str | None = None) -> ActiveJobPointer:
    return ActiveJobPointer(
        job_id=job_id or str(uuid.uuid4()),
        status=ChatActiveJobStatus.RUNNING,
        started_at=datetime(2026, 5, 15, 12, 0, 0, tzinfo=UTC),
    )


def _patch_session_repo(pointer: ActiveJobPointer | None) -> Any:
    """Patch ``BUDSectionSessionRepository`` so its instance returns ``pointer``."""
    repo = MagicMock()
    repo.get_active_job_pointer = AsyncMock(return_value=pointer)
    repo.clear_active_job = AsyncMock(return_value=None)
    return patch(
        "app.api.v1.bud_chat.BUDSectionSessionRepository",
        return_value=repo,
    ), repo


@pytest.mark.asyncio
async def test_active_chat_job_returns_none_when_no_pointer() -> None:
    """No durable pointer → endpoint returns None (renders as JSON ``null``)."""
    user = make_user()
    db = MagicMock()
    db.commit = AsyncMock()
    repo_ctx, repo = _patch_session_repo(None)
    with repo_ctx:
        out = await get_active_chat_job(
            bud_id=uuid.uuid4(),
            section="requirements_md",
            design_id=None,
            current_user=user,
            db=db,
        )
    assert out is None
    repo.get_active_job_pointer.assert_awaited_once()
    repo.clear_active_job.assert_not_called()


@pytest.mark.asyncio
async def test_active_chat_job_returns_live_status_when_pointer_alive() -> None:
    """Pointer + in-memory entry alive → endpoint returns the live status."""
    user = make_user()
    db = MagicMock()
    db.commit = AsyncMock()
    pointer = _make_pointer()
    expected = _make_running_status(job_id=pointer.job_id)
    repo_ctx, repo = _patch_session_repo(pointer)
    with repo_ctx, patch("app.api.v1.bud_chat.get_job", return_value=expected):
        out = await get_active_chat_job(
            bud_id=uuid.uuid4(),
            section="requirements_md",
            design_id=None,
            current_user=user,
            db=db,
        )
    assert out is expected
    repo.clear_active_job.assert_not_called()


@pytest.mark.asyncio
async def test_active_chat_job_clears_stale_pointer_when_job_missing() -> None:
    """Pointer present but in-memory entry gone → clear lazily, return None.

    Models a backend restart between worker exit and the next remount:
    the durable pointer survives, but ``_job_store`` is empty. The
    endpoint releases the claim so the next ``POST /chat`` isn't stuck
    at 409 ``chat_in_progress``.
    """
    user = make_user()
    db = MagicMock()
    db.commit = AsyncMock()
    pointer = _make_pointer()
    repo_ctx, repo = _patch_session_repo(pointer)
    with repo_ctx, patch("app.api.v1.bud_chat.get_job", return_value=None):
        out = await get_active_chat_job(
            bud_id=uuid.uuid4(),
            section="requirements_md",
            design_id=None,
            current_user=user,
            db=db,
        )
    assert out is None
    repo.clear_active_job.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.parametrize(
    "terminal_state", [JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED]
)
@pytest.mark.asyncio
async def test_active_chat_job_clears_stale_pointer_for_terminal_state(
    terminal_state: JobState,
) -> None:
    """Pointer present but in-memory entry is terminal → clear, return None.

    Covers the brief window between the worker's terminal ``update_job``
    publish and ``_clear_active_chat_claim`` in the ``finally``.
    """
    user = make_user()
    db = MagicMock()
    db.commit = AsyncMock()
    pointer = _make_pointer()
    terminal_status = JobStatusRead(
        job_id=pointer.job_id,
        job_type="bud_chat",
        state=terminal_state,
        status_message="done",
    )
    repo_ctx, repo = _patch_session_repo(pointer)
    with repo_ctx, patch("app.api.v1.bud_chat.get_job", return_value=terminal_status):
        out = await get_active_chat_job(
            bud_id=uuid.uuid4(),
            section="requirements_md",
            design_id=None,
            current_user=user,
            db=db,
        )
    assert out is None
    repo.clear_active_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_active_chat_job_pointer_lookup_scoped_by_args() -> None:
    """The pointer lookup is called with the exact ``(bud, section, design_id)`` triple."""
    user = make_user()
    db = MagicMock()
    db.commit = AsyncMock()
    bud_id = uuid.uuid4()
    design_id = uuid.uuid4()
    repo_ctx, repo = _patch_session_repo(None)
    with repo_ctx:
        await get_active_chat_job(
            bud_id=bud_id,
            section="design",
            design_id=design_id,
            current_user=user,
            db=db,
        )
    repo.get_active_job_pointer.assert_awaited_once_with(bud_id, "design", design_id)
