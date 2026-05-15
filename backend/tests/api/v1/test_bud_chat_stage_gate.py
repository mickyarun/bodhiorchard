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

"""Stage-gate (409) tests for the BUD chat endpoint.

Asserts that a chat request whose section is not allowed in the BUD's
current ``status`` is rejected with no DB write and no job enqueue.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.bud_chat import BUDChatRequest, chat_bud
from tests.api.v1._bud_chat_helpers import make_bud, make_user, patch_repos


@pytest.mark.asyncio
async def test_chat_bud_409_when_design_section_outside_design_stage() -> None:
    """Design chat in ``bud`` stage → 409, no DB writes, no job."""
    user = make_user()
    bud = make_bud(status="bud")
    db = MagicMock()
    patches = patch_repos(bud=bud)

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
        patch("app.api.v1.bud_chat.create_job_with_id") as create_job,
        pytest.raises(HTTPException) as ei,
    ):
        await chat_bud(
            bud_id=bud.id,
            body=BUDChatRequest(message="hi", section="design"),
            current_user=user,
            db=db,
        )

    assert ei.value.status_code == 409
    assert "design" in ei.value.detail.lower()
    create_job.assert_not_called()
    # User message must NOT be persisted on the 409 path.
    patches["BUDChatMessageRepository"].return_value.add_message.assert_not_called()


@pytest.mark.asyncio
async def test_chat_bud_409_when_requirements_in_testing_stage() -> None:
    """Requirements chat in ``testing`` stage → 409 (allowed only in ``bud``)."""
    user = make_user()
    bud = make_bud(status="testing")
    db = MagicMock()
    patches = patch_repos(bud=bud)

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
        patch("app.api.v1.bud_chat.create_job_with_id"),
        pytest.raises(HTTPException) as ei,
    ):
        await chat_bud(
            bud_id=bud.id,
            body=BUDChatRequest(message="hi", section="requirements_md"),
            current_user=user,
            db=db,
        )
    assert ei.value.status_code == 409


@pytest.mark.asyncio
async def test_chat_bud_409_when_requirements_in_design_stage() -> None:
    """Requirements chat in ``design`` stage → 409.

    Strict one-stage-per-section mirror of the edit-lock contract:
    requirements are only chatted on while the BUD is in ``bud`` status.
    """
    user = make_user()
    bud = make_bud(status="design")
    db = MagicMock()
    patches = patch_repos(bud=bud)

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
        patch("app.api.v1.bud_chat.create_job_with_id"),
        pytest.raises(HTTPException) as ei,
    ):
        await chat_bud(
            bud_id=bud.id,
            body=BUDChatRequest(message="hi", section="requirements_md"),
            current_user=user,
            db=db,
        )
    assert ei.value.status_code == 409


@pytest.mark.asyncio
async def test_chat_bud_409_when_tech_spec_outside_tech_arch_stage() -> None:
    """Tech-spec chat in ``design`` stage → 409 (allowed only in ``tech_arch``)."""
    user = make_user()
    bud = make_bud(status="design")
    db = MagicMock()
    patches = patch_repos(bud=bud)

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
        patch("app.api.v1.bud_chat.create_job_with_id"),
        pytest.raises(HTTPException) as ei,
    ):
        await chat_bud(
            bud_id=bud.id,
            body=BUDChatRequest(message="hi", section="tech_spec_md"),
            current_user=user,
            db=db,
        )
    assert ei.value.status_code == 409


@pytest.mark.asyncio
async def test_chat_bud_409_when_section_locked_at_every_stage() -> None:
    """Chat on a section absent from the gate map → 409, "not available".

    ``test_plan_md`` and ``code_review`` have no entry in
    ``SECTION_REQUIRED_STAGES``; the handler must surface a "chat not
    available" message rather than recommending a target stage.
    """
    user = make_user()
    bud = make_bud(status="testing")
    db = MagicMock()
    patches = patch_repos(bud=bud)

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
        patch("app.api.v1.bud_chat.create_job_with_id"),
        pytest.raises(HTTPException) as ei,
    ):
        await chat_bud(
            bud_id=bud.id,
            body=BUDChatRequest(message="hi", section="test_plan_md"),
            current_user=user,
            db=db,
        )
    assert ei.value.status_code == 409
    assert "not available" in ei.value.detail.lower()
