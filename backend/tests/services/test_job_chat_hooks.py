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

"""Worker-hook tests for ``handle_chat_job``.

Phase 2 added two best-effort hooks around ``_run_chat_job``:
``_mark_active_job_running`` on entry and ``_clear_active_chat_claim``
in the ``finally``. The hooks keep the durable ``bud_section_sessions``
claim row in sync with the in-flight job and must run regardless of how
the inner run ended (success, failure via ``update_job``, cancellation,
or an unhandled exception). These tests pin that contract.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.job_chat import handle_chat_job


def _payload() -> dict[str, Any]:
    return {
        "bud_id": str(uuid.uuid4()),
        "org_id": str(uuid.uuid4()),
        "bud_number": 1,
        "section": "requirements_md",
        "current_content": "spec",
        "title": "T",
        "message": "hi",
    }


def _patch_section_repo() -> tuple[MagicMock, Any]:
    """Return (mock_repo_instance, patch_ctx) for ``BUDSectionSessionRepository``.

    The ``handle_chat_job`` wrappers each construct a fresh repo per call,
    so the patch returns the same instance for every constructor call —
    the tests then assert on its method-mocks.
    """
    repo = MagicMock()
    repo.mark_active_job_running = AsyncMock(return_value=None)
    repo.clear_active_job = AsyncMock(return_value=None)
    ctx = patch(
        "app.services.job_chat.BUDSectionSessionRepository",
        return_value=repo,
    )
    return repo, ctx


def _patch_session() -> Any:
    """Patch ``AsyncSessionLocal`` so hooks can ``async with`` it cheaply."""
    session = MagicMock()
    session.commit = AsyncMock(return_value=None)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return patch(
        "app.services.job_chat.AsyncSessionLocal",
        return_value=session,
    )


@pytest.mark.asyncio
async def test_hooks_run_on_happy_path() -> None:
    """Successful run → both mark-running and clear-claim fire exactly once."""
    repo, repo_ctx = _patch_section_repo()
    with (
        _patch_session(),
        repo_ctx,
        patch(
            "app.services.job_chat._run_chat_job",
            new=AsyncMock(return_value=None),
        ),
    ):
        await handle_chat_job("job-1", _payload())

    repo.mark_active_job_running.assert_awaited_once()
    repo.clear_active_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_clear_runs_when_inner_raises() -> None:
    """Inner ``_run_chat_job`` raises → ``finally`` still clears the claim."""
    repo, repo_ctx = _patch_section_repo()
    with (
        _patch_session(),
        repo_ctx,
        patch(
            "app.services.job_chat._run_chat_job",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        pytest.raises(RuntimeError, match="boom"),
    ):
        await handle_chat_job("job-2", _payload())

    repo.clear_active_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_clear_runs_on_cancellation() -> None:
    """Inner cancelled → clear runs, cancel marker persists, error propagates.

    The persisted marker is what makes a cancel visible after a page
    refresh: the user-prompt row already exists in chat_history (saved
    by ``POST /chat``), and this AI-side row anchors the "Cancelled by
    user" answer so the thread doesn't look orphaned on reload.
    """
    repo, repo_ctx = _patch_section_repo()
    with (
        _patch_session(),
        repo_ctx,
        patch(
            "app.services.job_chat._run_chat_job",
            new=AsyncMock(side_effect=asyncio.CancelledError()),
        ),
        patch("app.services.job_chat.persist_chat_message", new=AsyncMock()) as persist,
        pytest.raises(asyncio.CancelledError),
    ):
        await handle_chat_job("job-3", _payload())

    repo.clear_active_job.assert_awaited_once()
    persist.assert_awaited_once()
    kwargs = persist.call_args.kwargs
    args = persist.call_args.args
    # Match against the positional contract used in _persist_cancel_marker.
    assert args[3] == "ai"
    assert args[4] == "Cancelled by user"
    # session_id is forwarded from the payload so the row groups with the
    # user's prompt under chat-history's session filter.
    assert "session_id" in kwargs


@pytest.mark.asyncio
async def test_cancel_marker_failure_does_not_mask_cancelled_error() -> None:
    """Persist marker failing is logged; CancelledError still propagates."""
    repo, repo_ctx = _patch_section_repo()
    with (
        _patch_session(),
        repo_ctx,
        patch(
            "app.services.job_chat._run_chat_job",
            new=AsyncMock(side_effect=asyncio.CancelledError()),
        ),
        patch(
            "app.services.job_chat.persist_chat_message",
            new=AsyncMock(side_effect=RuntimeError("db hiccup")),
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await handle_chat_job("job-cancel-marker-fail", _payload())

    repo.clear_active_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_failure_does_not_block_run() -> None:
    """``mark_active_job_running`` failing is logged and swallowed.

    The inner run still executes; the clear hook still runs in finally.
    """
    repo, repo_ctx = _patch_section_repo()
    repo.mark_active_job_running = AsyncMock(side_effect=RuntimeError("db hiccup"))
    inner = AsyncMock(return_value=None)
    with (
        _patch_session(),
        repo_ctx,
        patch("app.services.job_chat._run_chat_job", new=inner),
    ):
        await handle_chat_job("job-4", _payload())

    inner.assert_awaited_once()
    repo.clear_active_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_clear_failure_does_not_mask_inner_exception() -> None:
    """Clear hook failure is logged but does not swallow the inner error."""
    repo, repo_ctx = _patch_section_repo()
    repo.clear_active_job = AsyncMock(side_effect=RuntimeError("db hiccup"))
    with (
        _patch_session(),
        repo_ctx,
        patch(
            "app.services.job_chat._run_chat_job",
            new=AsyncMock(side_effect=ValueError("inner")),
        ),
        pytest.raises(ValueError, match="inner"),
    ):
        await handle_chat_job("job-5", _payload())
