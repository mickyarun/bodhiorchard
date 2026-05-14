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

"""Statement-shape tests for :class:`BUDSectionSessionRepository`.

These follow the same AsyncMock + statement-inspection pattern used
elsewhere in ``backend/tests/services`` for repository assertions. They
cover the bits that are easy to silently break: the ``design_id`` NULL
predicate (so non-design rows aren't accidentally filtered by a
``design_id = NULL`` which is always false), the rotation reset, and
the upsert branching.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.bud_section_session import BUDSectionSession
from app.repositories.bud_section_session import BUDSectionSessionRepository


def _make_repo(scalar_result: Any) -> tuple[BUDSectionSessionRepository, MagicMock]:
    """Build a repo whose ``db.execute().scalar_one_or_none()`` returns ``scalar_result``."""
    db = MagicMock()
    result_obj = MagicMock()
    result_obj.scalar_one_or_none.return_value = scalar_result
    db.execute = AsyncMock(return_value=result_obj)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    repo = BUDSectionSessionRepository(db, org_id=uuid.uuid4())
    return repo, db


@pytest.mark.asyncio
async def test_get_active_filters_design_id_is_null_when_omitted() -> None:
    """Non-design lookup must use ``design_id IS NULL`` (not ``= NULL``)."""
    repo, db = _make_repo(None)
    bud_id = uuid.uuid4()

    await repo.get_active(bud_id, "requirements_md")

    sent_stmt = db.execute.await_args.args[0]
    rendered = str(sent_stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "design_id IS NULL" in rendered.replace('"', "")


@pytest.mark.asyncio
async def test_get_active_uses_equality_when_design_id_supplied() -> None:
    """Design-section lookups bind ``design_id = :design_id``."""
    repo, db = _make_repo(None)
    bud_id = uuid.uuid4()
    design_id = uuid.uuid4()

    await repo.get_active(bud_id, "design", design_id=design_id)

    sent_stmt = db.execute.await_args.args[0]
    rendered = str(sent_stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "design_id IS NULL" not in rendered.replace('"', "")
    assert "design_id" in rendered


@pytest.mark.asyncio
async def test_upsert_creates_row_when_absent() -> None:
    """Missing row → ``db.add`` + flush + refresh (BaseRepository.create)."""
    repo, db = _make_repo(None)
    db.add = MagicMock()
    bud_id = uuid.uuid4()
    session_id = uuid.uuid4()

    row = await repo.upsert(bud_id, "tech_spec_md", session_id)

    db.add.assert_called_once()
    assert isinstance(row, BUDSectionSession)
    assert row.session_id == session_id
    assert row.message_count == 0


@pytest.mark.asyncio
async def test_upsert_updates_in_place_when_row_exists() -> None:
    """Existing row → mutate ``session_id`` and zero ``message_count``."""
    existing = BUDSectionSession(
        org_id=uuid.uuid4(),
        bud_id=uuid.uuid4(),
        section="design",
        design_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        message_count=7,
    )
    repo, db = _make_repo(existing)
    db.add = MagicMock()
    new_session_id = uuid.uuid4()

    row = await repo.upsert(
        existing.bud_id,
        "design",
        new_session_id,
        design_id=existing.design_id,
    )

    db.add.assert_not_called()
    assert row is existing
    assert row.session_id == new_session_id
    assert row.message_count == 0


@pytest.mark.asyncio
async def test_rotate_resets_message_count_and_swaps_session_id() -> None:
    """``rotate`` writes the new id and zeros the counter."""
    existing = BUDSectionSession(
        org_id=uuid.uuid4(),
        bud_id=uuid.uuid4(),
        section="requirements_md",
        design_id=None,
        session_id=uuid.uuid4(),
        message_count=20,
    )
    existing.id = uuid.uuid4()
    repo, _db = _make_repo(existing)
    new_session_id = uuid.uuid4()

    rotated = await repo.rotate(existing.id, new_session_id)

    assert rotated is existing
    assert rotated.session_id == new_session_id
    assert rotated.message_count == 0


@pytest.mark.asyncio
async def test_rotate_returns_none_when_row_missing() -> None:
    """If the row has been deleted, ``rotate`` quietly returns ``None``."""
    repo, _db = _make_repo(None)
    rotated = await repo.rotate(uuid.uuid4(), uuid.uuid4())
    assert rotated is None


@pytest.mark.asyncio
async def test_increment_message_count_bumps_existing_row_by_one() -> None:
    """Counter goes from N to N+1; missing row is a quiet no-op."""
    row = BUDSectionSession(
        org_id=uuid.uuid4(),
        bud_id=uuid.uuid4(),
        section="design",
        design_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        message_count=4,
    )
    row.id = uuid.uuid4()
    repo, _db = _make_repo(row)

    await repo.increment_message_count(row.id)

    assert row.message_count == 5


@pytest.mark.asyncio
async def test_increment_message_count_silently_skips_missing_row() -> None:
    """No row → no exception, no DB write."""
    repo, db = _make_repo(None)
    await repo.increment_message_count(uuid.uuid4())
    db.flush.assert_not_awaited()
