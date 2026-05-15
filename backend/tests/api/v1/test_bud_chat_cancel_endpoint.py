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

"""Handler tests for ``POST /v1/buds/{bud_id}/chat/cancel``.

The service body is exercised in ``tests/services/test_bud_chat_cancel.py``;
these tests pin the HTTP-layer contract: 200 with the cancelled
job_id on success, 404 when no chat is in flight, 500 when the cancel
signal itself raises.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.bud_chat import cancel_active_chat
from app.services.bud_chat_cancel import BUDChatCancelError
from tests.api.v1._bud_chat_helpers import make_user


@pytest.mark.asyncio
async def test_cancel_returns_job_id_when_signal_lands() -> None:
    """Live cancel → 200 with the cancelled job_id in the body."""
    user = make_user()
    db = MagicMock()
    with patch("app.api.v1.bud_chat.cancel_chat", new=AsyncMock(return_value="job-abc")) as svc:
        out = await cancel_active_chat(
            bud_id=uuid.uuid4(),
            section="requirements_md",
            design_id=None,
            current_user=user,
            db=db,
        )

    assert out.cancelled_job_id == "job-abc"
    svc.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_404_when_no_active_chat() -> None:
    """Service returns None (no in-flight chat) → handler raises 404."""
    user = make_user()
    db = MagicMock()
    with (
        patch("app.api.v1.bud_chat.cancel_chat", new=AsyncMock(return_value=None)),
        pytest.raises(HTTPException) as exc_info,
    ):
        await cancel_active_chat(
            bud_id=uuid.uuid4(),
            section="requirements_md",
            design_id=None,
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert "No active chat" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_cancel_500_when_signal_raises() -> None:
    """``BUDChatCancelError`` → 500 with the underlying message.

    Preserves the exception chain via ``raise … from exc`` so the
    original traceback is available in logs.
    """
    user = make_user()
    db = MagicMock()
    boom = BUDChatCancelError("subprocess unreachable")
    with (
        patch("app.api.v1.bud_chat.cancel_chat", new=AsyncMock(side_effect=boom)),
        pytest.raises(HTTPException) as exc_info,
    ):
        await cancel_active_chat(
            bud_id=uuid.uuid4(),
            section="requirements_md",
            design_id=None,
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "subprocess unreachable"
    assert exc_info.value.__cause__ is boom


@pytest.mark.asyncio
async def test_cancel_passes_design_id_to_service() -> None:
    """Design-tab cancel → service receives the ``design_id`` argument."""
    user = make_user()
    db = MagicMock()
    bud_id = uuid.uuid4()
    design_id = uuid.uuid4()
    with patch("app.api.v1.bud_chat.cancel_chat", new=AsyncMock(return_value="job-d")) as svc:
        await cancel_active_chat(
            bud_id=bud_id,
            section="design",
            design_id=design_id,
            current_user=user,
            db=db,
        )

    svc.assert_awaited_once()
    kwargs = svc.call_args.kwargs
    assert kwargs["bud_id"] == bud_id
    assert kwargs["section"] == "design"
    assert kwargs["design_id"] == design_id
    assert kwargs["org_id"] == user.org_id
    # Pins the handler's hard-coded reason so a rename/refactor breaks
    # loudly instead of silently sending an empty string downstream.
    assert kwargs["reason"] == "Cancelled by user"
