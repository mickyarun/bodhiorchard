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

"""Concurrency-claim tests for the BUD chat endpoint.

Phase 2 of the AI Editor chat resume work added an atomic claim on
``bud_section_sessions.active_job_id`` to prevent two simultaneous
``POST /chat`` calls from racing each other on the same
``(bud, section, design)`` thread. These tests pin the handler-level
contract: a lost claim returns 409 ``chat_in_progress`` with the
in-flight pointer, never enqueues a job, and never persists a user
message; an enqueue failure after a won claim releases the pointer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.bud_chat import BUDChatRequest, chat_bud
from app.models.bud_section_session import ChatActiveJobStatus
from app.repositories.bud_section_session import ActiveJobPointer
from tests.api.v1._bud_chat_helpers import make_bud, make_user, patch_repos


@pytest.mark.asyncio
async def test_chat_in_progress_409_when_claim_lost() -> None:
    """Lost claim → 409 ``chat_in_progress`` with the in-flight pointer.

    No user message persisted, no job enqueued. The 409 detail carries
    the winning request's ``active_job_id`` + ``started_at`` so the
    frontend can subscribe to it and show live progress.
    """
    bud = make_bud(status="bud")
    started_at = datetime(2026, 5, 15, 12, 0, 0, tzinfo=UTC)
    pointer = ActiveJobPointer(
        job_id="winning-job-id",
        status=ChatActiveJobStatus.RUNNING,
        started_at=started_at,
    )
    patches = patch_repos(bud=bud, claim_won=False, active_pointer=pointer)

    db = MagicMock()
    db.flush = AsyncMock()
    user = make_user()
    with (  # noqa: SIM117 — one stack matches existing test style
        patch("app.api.v1.bud_chat.BUDRepository", patches["BUDRepository"]),
        patch(
            "app.api.v1.bud_chat.BUDSectionSessionRepository",
            patches["BUDSectionSessionRepository"],
        ),
        patch(
            "app.api.v1.bud_chat.BUDChatMessageRepository",
            patches["BUDChatMessageRepository"],
        ),
        patch(
            "app.api.v1.bud_chat.BUDDesignRepository",
            patches["BUDDesignRepository"],
        ),
        patch("app.api.v1.bud_chat.create_job_with_id") as enqueue,
        pytest.raises(HTTPException) as exc_info,
    ):
        await chat_bud(
            bud_id=bud.id,
            body=BUDChatRequest(message="hi", section="requirements_md"),
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "error": "chat_in_progress",
        "message": "A chat is already in progress for this section.",
        "active_job_id": "winning-job-id",
        "started_at": started_at.isoformat(),
    }
    # No job enqueued, no user-message persist.
    enqueue.assert_not_called()
    patches["BUDChatMessageRepository"].return_value.add_message.assert_not_called()


@pytest.mark.asyncio
async def test_chat_in_progress_409_with_missing_pointer() -> None:
    """Race: claim lost but pointer fetch returns None.

    Can happen if the winning job terminates between the lost claim and
    the follow-up ``get_active_job_pointer`` call. The handler still
    raises 409 — the active_job_id / started_at fields are simply null.
    """
    bud = make_bud(status="bud")
    patches = patch_repos(bud=bud, claim_won=False, active_pointer=None)

    db = MagicMock()
    db.flush = AsyncMock()
    user = make_user()
    with (  # noqa: SIM117
        patch("app.api.v1.bud_chat.BUDRepository", patches["BUDRepository"]),
        patch(
            "app.api.v1.bud_chat.BUDSectionSessionRepository",
            patches["BUDSectionSessionRepository"],
        ),
        patch(
            "app.api.v1.bud_chat.BUDChatMessageRepository",
            patches["BUDChatMessageRepository"],
        ),
        patch(
            "app.api.v1.bud_chat.BUDDesignRepository",
            patches["BUDDesignRepository"],
        ),
        patch("app.api.v1.bud_chat.create_job_with_id"),
        pytest.raises(HTTPException) as exc_info,
    ):
        await chat_bud(
            bud_id=bud.id,
            body=BUDChatRequest(message="hi", section="requirements_md"),
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["active_job_id"] is None
    assert exc_info.value.detail["started_at"] is None


@pytest.mark.asyncio
async def test_claim_released_when_enqueue_fails() -> None:
    """Enqueue raises after a won claim → ``clear_active_job`` runs.

    The pointer is released so a subsequent retry can claim it; the
    original exception is re-raised so the request fails loudly.
    """
    bud = make_bud(status="bud")
    server_session_id = uuid.uuid4()
    patches = patch_repos(bud=bud, claim_won=True, claim_session_id=server_session_id)

    db = MagicMock()
    db.flush = AsyncMock()
    user = make_user()
    boom = RuntimeError("queue full")
    with (  # noqa: SIM117
        patch("app.api.v1.bud_chat.BUDRepository", patches["BUDRepository"]),
        patch(
            "app.api.v1.bud_chat.BUDSectionSessionRepository",
            patches["BUDSectionSessionRepository"],
        ),
        patch(
            "app.api.v1.bud_chat.BUDChatMessageRepository",
            patches["BUDChatMessageRepository"],
        ),
        patch(
            "app.api.v1.bud_chat.BUDDesignRepository",
            patches["BUDDesignRepository"],
        ),
        patch("app.api.v1.bud_chat.create_job_with_id", side_effect=boom),
        pytest.raises(RuntimeError, match="queue full"),
    ):
        await chat_bud(
            bud_id=bud.id,
            body=BUDChatRequest(message="hi", section="requirements_md"),
            current_user=user,
            db=db,
        )

    session_repo = patches["BUDSectionSessionRepository"].return_value
    session_repo.clear_active_job.assert_awaited_once_with(bud.id, "requirements_md", None)
