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

"""Section-aware permission tests for the BUD chat endpoints.

The route-level dependency accepts either ``buds:edit`` or ``buds:test``
so the QA role can reach the handler at all; the per-section check
inside the handler then narrows access — ``buds:test`` only unlocks the
``testing`` section, not requirements / tech-spec / design.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.bud_chat import (
    BUDChatRequest,
    _assert_section_chat_permission,
    cancel_active_chat,
    chat_bud,
)
from tests.api.v1._bud_chat_helpers import make_bud, make_user, patch_repos


def _qa_perms() -> AsyncMock:
    """Stand-in for ``get_user_permissions`` returning the QA permission set."""
    return AsyncMock(return_value={"buds:view", "buds:test"})


@pytest.mark.asyncio
async def test_chat_bud_403_when_qa_targets_requirements_section() -> None:
    """QA role (``buds:test`` only) → 403 on the Requirements section.

    The route-level gate lets the request reach the handler, but the
    per-section check inside ``chat_bud`` rejects authorship sections
    that demand ``buds:edit``. No DB writes, no job enqueue.
    """
    user = make_user()
    bud = make_bud(status="bud")
    db = MagicMock()
    patches = patch_repos(bud=bud)

    with (
        patch("app.api.v1.bud_chat.get_user_permissions", new=_qa_perms()),
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
            body=BUDChatRequest(message="hi", section="requirements_md"),
            current_user=user,
            db=db,
        )

    assert ei.value.status_code == 403
    assert ei.value.detail == "Insufficient permissions."
    create_job.assert_not_called()
    patches["BUDChatMessageRepository"].return_value.add_message.assert_not_called()
    patches["BUDSectionSessionRepository"].return_value.try_claim_active_job.assert_not_called()


@pytest.mark.asyncio
async def test_assert_section_chat_permission_allows_qa_on_testing() -> None:
    """QA role → helper accepts the ``testing`` section without raising."""
    user = make_user()
    db = MagicMock()
    with patch("app.api.v1.bud_chat.get_user_permissions", new=_qa_perms()):
        await _assert_section_chat_permission(user, db, "testing")


@pytest.mark.parametrize("section", ["requirements_md", "tech_spec_md", "design"])
@pytest.mark.asyncio
async def test_assert_section_chat_permission_blocks_qa_on_author_sections(
    section: str,
) -> None:
    """QA role → helper raises 403 on every authoring section."""
    user = make_user()
    db = MagicMock()
    with (
        patch("app.api.v1.bud_chat.get_user_permissions", new=_qa_perms()),
        pytest.raises(HTTPException) as ei,
    ):
        await _assert_section_chat_permission(user, db, section)
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_assert_section_chat_permission_skips_unknown_section() -> None:
    """Unmapped sections (e.g. ``test_plan_md``) fall through — the
    stage-gate check downstream is responsible for rejecting them."""
    user = make_user()
    db = MagicMock()
    perms = AsyncMock(return_value={"buds:view"})  # nothing edit-ish
    with patch("app.api.v1.bud_chat.get_user_permissions", new=perms):
        await _assert_section_chat_permission(user, db, "test_plan_md")
    perms.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_403_when_qa_targets_requirements_section() -> None:
    """QA role → 403 on cancel for a section they cannot author.

    The cancel signal is never dispatched and the underlying service
    is never called.
    """
    user = make_user()
    db = MagicMock()
    with (
        patch("app.api.v1.bud_chat.get_user_permissions", new=_qa_perms()),
        patch("app.api.v1.bud_chat.cancel_chat", new=AsyncMock()) as svc,
        pytest.raises(HTTPException) as ei,
    ):
        await cancel_active_chat(
            bud_id=uuid.uuid4(),
            section="requirements_md",
            design_id=None,
            current_user=user,
            db=db,
        )

    assert ei.value.status_code == 403
    svc.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_allows_qa_on_testing_section() -> None:
    """QA role → cancel proceeds on ``testing`` and returns the job id."""
    user = make_user()
    db = MagicMock()
    with (
        patch("app.api.v1.bud_chat.get_user_permissions", new=_qa_perms()),
        patch(
            "app.api.v1.bud_chat.cancel_chat",
            new=AsyncMock(return_value="job-cancel-1"),
        ) as svc,
    ):
        out = await cancel_active_chat(
            bud_id=uuid.uuid4(),
            section="testing",
            design_id=None,
            current_user=user,
            db=db,
        )

    assert out.cancelled_job_id == "job-cancel-1"
    svc.assert_awaited_once()
