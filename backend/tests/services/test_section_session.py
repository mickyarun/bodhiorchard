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

"""Tests for :mod:`app.services.section_session` chat-turn resolution.

These exercise the three rules of ``resolve_chat_session``:

1. No existing row → claim a new id (``is_resume=False``).
2. ``message_count`` past the cap → rotate (``is_resume=False``,
   ``rotated=True``).
3. Existing under-cap row → reuse the id (``is_resume=True``).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.bud_constants import SECTION_SESSION_MESSAGE_CAP
from app.services import section_session


def _patch_async_session_local(
    repo_mock: MagicMock,
) -> tuple[Any, Any]:
    """Patch ``AsyncSessionLocal`` + repo class so resolution runs without a real DB."""

    @asynccontextmanager
    async def _fake_session() -> AsyncIterator[MagicMock]:
        db = MagicMock()
        db.commit = AsyncMock()
        yield db

    return (
        patch.object(section_session, "AsyncSessionLocal", _fake_session),
        patch.object(section_session, "BUDSectionSessionRepository", return_value=repo_mock),
    )


@pytest.mark.asyncio
async def test_resolve_chat_session_claims_when_row_missing() -> None:
    """Missing row → mint + upsert + ``is_resume=False``."""
    repo = MagicMock()
    repo.get_active = AsyncMock(return_value=None)
    repo.upsert = AsyncMock()

    patches = _patch_async_session_local(repo)
    with patches[0], patches[1]:
        resolved = await section_session.resolve_chat_session(
            org_id=uuid.uuid4(),
            bud_id=uuid.uuid4(),
            section="requirements_md",
        )

    assert resolved.is_resume is False
    assert resolved.rotated is False
    repo.upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_chat_session_rotates_at_cap() -> None:
    """``message_count >= cap`` → ``rotate`` is called, response says ``rotated``."""
    existing = MagicMock()
    existing.id = uuid.uuid4()
    existing.session_id = uuid.uuid4()
    existing.message_count = SECTION_SESSION_MESSAGE_CAP

    rotated_row = MagicMock()
    rotated_row.session_id = uuid.uuid4()

    repo = MagicMock()
    repo.get_active = AsyncMock(return_value=existing)
    repo.rotate = AsyncMock(return_value=rotated_row)

    patches = _patch_async_session_local(repo)
    with patches[0], patches[1]:
        resolved = await section_session.resolve_chat_session(
            org_id=uuid.uuid4(),
            bud_id=uuid.uuid4(),
            section="tech_spec_md",
        )

    assert resolved.is_resume is False
    assert resolved.rotated is True
    assert resolved.session_id == rotated_row.session_id


@pytest.mark.asyncio
async def test_resolve_chat_session_resumes_under_cap() -> None:
    """Under-cap existing row → reuse id, ``is_resume=True``."""
    existing = MagicMock()
    existing.id = uuid.uuid4()
    existing.session_id = uuid.uuid4()
    existing.message_count = SECTION_SESSION_MESSAGE_CAP - 1

    repo = MagicMock()
    repo.get_active = AsyncMock(return_value=existing)
    repo.rotate = AsyncMock()  # must NOT be called

    patches = _patch_async_session_local(repo)
    with patches[0], patches[1]:
        resolved = await section_session.resolve_chat_session(
            org_id=uuid.uuid4(),
            bud_id=uuid.uuid4(),
            section="design",
            design_id=uuid.uuid4(),
        )

    assert resolved.is_resume is True
    assert resolved.rotated is False
    assert resolved.session_id == existing.session_id
    repo.rotate.assert_not_called()


@pytest.mark.asyncio
async def test_bump_chat_session_count_calls_increment() -> None:
    """``bump_chat_session_count`` increments the active row."""
    existing = MagicMock()
    existing.id = uuid.uuid4()

    repo = MagicMock()
    repo.get_active = AsyncMock(return_value=existing)
    repo.increment_message_count = AsyncMock()

    patches = _patch_async_session_local(repo)
    with patches[0], patches[1]:
        await section_session.bump_chat_session_count(
            org_id=uuid.uuid4(),
            bud_id=uuid.uuid4(),
            section="requirements_md",
        )

    repo.increment_message_count.assert_awaited_once_with(existing.id)


@pytest.mark.asyncio
async def test_bump_chat_session_count_silently_skips_missing_row() -> None:
    """No active row → no exception, increment never called."""
    repo = MagicMock()
    repo.get_active = AsyncMock(return_value=None)
    repo.increment_message_count = AsyncMock()

    patches = _patch_async_session_local(repo)
    with patches[0], patches[1]:
        await section_session.bump_chat_session_count(
            org_id=uuid.uuid4(),
            bud_id=uuid.uuid4(),
            section="design",
        )

    repo.increment_message_count.assert_not_called()
