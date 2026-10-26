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
the upsert's ON CONFLICT target.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

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


async def _rendered_upsert(design_id: uuid.UUID | None) -> str:
    """Run ``upsert`` against a mocked session and render the SQL it sent."""
    repo, db = _make_repo(MagicMock())
    await repo.upsert(uuid.uuid4(), "design", uuid.uuid4(), design_id=design_id)
    return str(db.execute.await_args.args[0].compile(dialect=postgresql.dialect()))


@pytest.mark.asyncio
async def test_upsert_section_thread_targets_the_null_design_index() -> None:
    """``design_id`` NULL conflicts on (bud_id, section) WHERE design_id IS NULL."""
    rendered = await _rendered_upsert(None)

    assert rendered.startswith("INSERT INTO bud_section_sessions")
    assert "ON CONFLICT (bud_id, section) WHERE design_id IS NULL DO UPDATE" in rendered
    assert "RETURNING" in rendered


@pytest.mark.asyncio
async def test_upsert_design_thread_targets_the_design_index() -> None:
    """A design thread conflicts on (bud_id, section, design_id) WHERE NOT NULL."""
    rendered = await _rendered_upsert(uuid.uuid4())

    assert (
        "ON CONFLICT (bud_id, section, design_id) WHERE design_id IS NOT NULL DO UPDATE"
        in rendered
    )


@pytest.mark.asyncio
async def test_upsert_resets_session_and_count_on_conflict() -> None:
    """The update swaps ``session_id``, zeroes ``message_count`` and bumps ``updated_at``."""
    update_clause = (await _rendered_upsert(None)).split("DO UPDATE SET", 1)[1]

    assert "session_id =" in update_clause
    assert "message_count =" in update_clause
    assert "updated_at = now()" in update_clause


@pytest.mark.asyncio
async def test_upsert_raises_when_thread_row_is_another_orgs() -> None:
    """An empty RETURNING means the org guard skipped the update: raise, don't hide it."""
    repo, _ = _make_repo(None)

    with pytest.raises(ValueError, match="belongs to another org"):
        await repo.upsert(uuid.uuid4(), "requirements_md", uuid.uuid4())


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
