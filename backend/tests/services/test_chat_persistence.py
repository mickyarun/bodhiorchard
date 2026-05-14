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

"""Tests for chat persistence — confirms section content writes go through
the row-locked ``get_by_id_for_update`` path so concurrent edits on the
same BUD/section serialize at the DB.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import chat_persistence


@pytest.mark.asyncio
async def test_persist_chat_update_uses_for_update_lock() -> None:
    """The BUD is fetched via ``get_by_id_for_update``, not the plain getter."""
    bud = MagicMock()
    bud.requirements_md = "old"

    repo = MagicMock()
    repo.get_by_id_for_update = AsyncMock(return_value=bud)
    repo.get_by_id = AsyncMock(return_value=bud)  # must NOT be called

    @asynccontextmanager
    async def _fake_session() -> AsyncIterator[MagicMock]:
        db = MagicMock()
        db.commit = AsyncMock()
        yield db

    with (
        patch.object(chat_persistence, "AsyncSessionLocal", _fake_session),
        patch.object(chat_persistence, "BUDRepository", return_value=repo),
    ):
        await chat_persistence.persist_chat_update(
            str(uuid.uuid4()),
            str(uuid.uuid4()),
            "requirements_md",
            "new content",
        )

    repo.get_by_id_for_update.assert_awaited_once()
    repo.get_by_id.assert_not_called()
    assert bud.requirements_md == "new content"


@pytest.mark.asyncio
async def test_persist_chat_update_handles_missing_bud() -> None:
    """If the BUD is gone (cascade), no setattr is attempted."""
    repo = MagicMock()
    repo.get_by_id_for_update = AsyncMock(return_value=None)

    @asynccontextmanager
    async def _fake_session() -> AsyncIterator[MagicMock]:
        db = MagicMock()
        db.commit = AsyncMock()
        yield db

    with (
        patch.object(chat_persistence, "AsyncSessionLocal", _fake_session),
        patch.object(chat_persistence, "BUDRepository", return_value=repo),
    ):
        # Should not raise.
        await chat_persistence.persist_chat_update(
            str(uuid.uuid4()),
            str(uuid.uuid4()),
            "requirements_md",
            "irrelevant",
        )

    repo.get_by_id_for_update.assert_awaited_once()
