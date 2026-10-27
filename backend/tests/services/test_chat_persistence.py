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
same BUD/section serialize at the DB, and that each real edit leaves a
pre-edit snapshot for the History tab.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.bud import BUDStatus
from app.models.bud_version import BUDEditSource
from app.repositories import bud_version as bud_version_repo
from app.services import chat_persistence


@asynccontextmanager
async def _fake_session() -> AsyncIterator[MagicMock]:
    db = MagicMock()
    db.commit = AsyncMock()
    yield db


def _locked_repo(bud: MagicMock) -> MagicMock:
    repo = MagicMock()
    repo.get_by_id_for_update = AsyncMock(return_value=bud)
    return repo


@pytest.mark.asyncio
async def test_persist_chat_update_uses_for_update_lock() -> None:
    """The BUD is fetched via ``get_by_id_for_update``, not the plain getter."""
    bud = MagicMock()
    bud.requirements_md = "old"

    repo = MagicMock()
    repo.get_by_id_for_update = AsyncMock(return_value=bud)
    repo.get_by_id = AsyncMock(return_value=bud)  # must NOT be called

    with (
        patch.object(chat_persistence, "AsyncSessionLocal", _fake_session),
        patch.object(chat_persistence, "BUDRepository", return_value=repo),
        patch.object(bud_version_repo, "commit_snapshot", AsyncMock()),
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


@pytest.mark.asyncio
async def test_persist_chat_update_snapshots_pre_edit_content() -> None:
    """A chat edit records one history row holding the text it replaced."""
    user_id = uuid.uuid4()
    bud = MagicMock(id=uuid.uuid4(), status=BUDStatus.BUD, title="Demo")
    bud.requirements_md = "user-written description"
    commit = AsyncMock()

    with (
        patch.object(chat_persistence, "AsyncSessionLocal", _fake_session),
        patch.object(chat_persistence, "BUDRepository", return_value=_locked_repo(bud)),
        patch.object(bud_version_repo, "commit_snapshot", commit),
    ):
        await chat_persistence.persist_chat_update(
            str(bud.id),
            str(uuid.uuid4()),
            "requirements_md",
            "chat rewrite",
            user_id=str(user_id),
        )

    commit.assert_awaited_once()
    kwargs = commit.await_args.kwargs
    assert kwargs["snapshot"]["requirements_md"] == "user-written description"
    assert kwargs["source"] == BUDEditSource.AGENT
    assert kwargs["edited_by"] == user_id
    assert kwargs["phase"] == BUDStatus.BUD
    assert kwargs["reason"] == "chat edit"
    assert bud.requirements_md == "chat rewrite"


@pytest.mark.asyncio
async def test_persist_chat_update_files_snapshot_under_section_phase() -> None:
    """A tech-spec chat that lands after the BUD advanced stays in Tech Spec history."""
    bud = MagicMock(id=uuid.uuid4(), status=BUDStatus.DEVELOPMENT)
    bud.tech_spec_md = "old spec"
    commit = AsyncMock()

    with (
        patch.object(chat_persistence, "AsyncSessionLocal", _fake_session),
        patch.object(chat_persistence, "BUDRepository", return_value=_locked_repo(bud)),
        patch.object(bud_version_repo, "commit_snapshot", commit),
        patch.object(chat_persistence, "apply_tech_spec_edit", AsyncMock()),
    ):
        await chat_persistence.persist_chat_update(
            str(bud.id),
            str(uuid.uuid4()),
            "tech_spec_md",
            "new spec",
        )

    commit.assert_awaited_once()
    assert commit.await_args.kwargs["phase"] == BUDStatus.TECH_ARCH
    assert commit.await_args.kwargs["snapshot"]["tech_spec_md"] == "old spec"


@pytest.mark.asyncio
async def test_persist_chat_update_unchanged_content_skips_snapshot() -> None:
    """A chat reply that returns the same text adds no history row."""
    bud = MagicMock(id=uuid.uuid4(), status=BUDStatus.BUD)
    bud.requirements_md = "same text"
    commit = AsyncMock()

    with (
        patch.object(chat_persistence, "AsyncSessionLocal", _fake_session),
        patch.object(chat_persistence, "BUDRepository", return_value=_locked_repo(bud)),
        patch.object(bud_version_repo, "commit_snapshot", commit),
    ):
        await chat_persistence.persist_chat_update(
            str(bud.id),
            str(uuid.uuid4()),
            "requirements_md",
            "same text",
        )

    commit.assert_not_awaited()
