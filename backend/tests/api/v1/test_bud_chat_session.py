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

"""Session-resolution tests for the BUD chat endpoint.

Asserts that the *server*'s view of the active section session id —
the row in ``bud_section_sessions`` — wins over any client-supplied
id, and that the first-turn path (no row yet) falls back to an empty
session id in the response so the worker can mint one.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.bud_chat import BUDChatRequest, chat_bud
from tests.api.v1._bud_chat_helpers import make_bud, make_user, patch_repos


@pytest.mark.asyncio
async def test_chat_bud_happy_path_uses_resolved_session_id() -> None:
    """Existing section session → response carries that id, not the body's."""
    user = make_user()
    bud = make_bud(status="design")
    db = MagicMock()
    db.flush = AsyncMock()

    server_session_id = uuid.uuid4()
    active_session = MagicMock()
    active_session.session_id = server_session_id

    fake_job = MagicMock()
    fake_job.job_id = "job-123"

    patches = patch_repos(bud=bud, active_session=active_session)

    with (
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
        patch("app.api.v1.bud_chat.create_job", return_value=fake_job),
    ):
        response = await chat_bud(
            bud_id=bud.id,
            body=BUDChatRequest(
                message="iterate",
                section="design",
                session_id=uuid.uuid4(),  # client-supplied id is IGNORED
            ),
            current_user=user,
            db=db,
        )

    assert response.session_id == str(server_session_id)
    assert response.job_id == "job-123"
    # User message tagged with the SERVER session id, not the client's.
    add_kwargs = patches["BUDChatMessageRepository"].return_value.add_message.await_args.kwargs
    assert add_kwargs["session_id"] == server_session_id


@pytest.mark.asyncio
async def test_chat_bud_first_message_falls_back_to_body_session_id() -> None:
    """No active row + no body id → response carries empty session id.

    The worker will mint one on first run; the endpoint accepts that the
    user-message row may carry ``session_id=None`` for the very first
    turn (the AI reply row will pick up the worker-resolved id).
    """
    user = make_user()
    bud = make_bud(status="design")
    db = MagicMock()
    db.flush = AsyncMock()

    fake_job = MagicMock()
    fake_job.job_id = "job-456"

    patches = patch_repos(bud=bud, active_session=None)

    with (
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
        patch("app.api.v1.bud_chat.create_job", return_value=fake_job),
    ):
        response = await chat_bud(
            bud_id=bud.id,
            body=BUDChatRequest(message="first", section="design"),
            current_user=user,
            db=db,
        )

    assert response.session_id == ""
