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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.bud_chat import BUDChatRequest, chat_bud
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
