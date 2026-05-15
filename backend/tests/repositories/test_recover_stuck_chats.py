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

"""Statement-shape tests for :func:`recover_stuck_chats`.

The function is the boot-time orphan sweep for in-flight chat jobs
that didn't survive the prior backend process. Tests pin three
behaviours:

1. **Empty** — when no row has ``active_job_id IS NOT NULL`` the
   function short-circuits to 0 with no further DB writes.
2. **Single orphan** — SELECT yields one row, INSERT writes one
   marker, UPDATE clears the pointer scoped to that row's id.
3. **Multiple orphans** — INSERT receives N rows, UPDATE's
   ``IN`` predicate carries all N ids.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.bud_section_session import (
    CHAT_INTERRUPTED_MESSAGE,
    recover_stuck_chats,
)


def _orphan(
    *,
    session_id: uuid.UUID | None = None,
    design_id: uuid.UUID | None = None,
) -> MagicMock:
    """Build a single SELECT-row stand-in carrying the orphan tuple."""
    row = MagicMock()
    row.id = uuid.uuid4()
    row.org_id = uuid.uuid4()
    row.bud_id = uuid.uuid4()
    row.section = "requirements_md"
    row.design_id = design_id
    row.session_id = session_id or uuid.uuid4()
    return row


def _make_db(select_rows: Iterable[MagicMock], update_rowcount: int) -> MagicMock:
    """Build an AsyncSession mock that yields ``select_rows`` then a stub UPDATE result."""
    db = MagicMock()
    db.flush = AsyncMock()

    select_result = MagicMock()
    select_result.all.return_value = list(select_rows)

    update_result = MagicMock()
    update_result.rowcount = update_rowcount

    execute_returns: list[Any] = [select_result]
    # INSERT and UPDATE both go through ``db.execute``; the function
    # consumes the SELECT first, ignores the INSERT result, and reads
    # the rowcount from the UPDATE result. Provide stubs in order.
    execute_returns.extend([MagicMock(), update_result])
    db.execute = AsyncMock(side_effect=execute_returns)
    return db


@pytest.mark.asyncio
async def test_returns_zero_when_no_orphans() -> None:
    """Empty SELECT → 0, no INSERT/UPDATE/flush."""
    db = _make_db(select_rows=[], update_rowcount=0)

    out = await recover_stuck_chats(db)

    assert out == 0
    # SELECT only — no further execute calls.
    assert db.execute.await_count == 1
    db.flush.assert_not_called()


@pytest.mark.asyncio
async def test_single_orphan_inserts_marker_and_clears_pointer() -> None:
    """One orphan → INSERT one marker, UPDATE one pointer, return 1."""
    orphan = _orphan()
    db = _make_db(select_rows=[orphan], update_rowcount=1)

    out = await recover_stuck_chats(db)

    assert out == 1
    assert db.execute.await_count == 3  # SELECT, INSERT, UPDATE
    db.flush.assert_awaited_once()

    # INSERT call gets a list of dicts as its second positional arg.
    insert_call = db.execute.await_args_list[1]
    marker_rows = insert_call.args[1]
    assert len(marker_rows) == 1
    assert marker_rows[0]["role"] == "ai"
    assert marker_rows[0]["message"] == CHAT_INTERRUPTED_MESSAGE
    assert marker_rows[0]["session_id"] == orphan.session_id
    assert marker_rows[0]["bud_id"] == orphan.bud_id


@pytest.mark.asyncio
async def test_multiple_orphans_inserts_all_markers() -> None:
    """N orphans → N markers in one INSERT, UPDATE returns N."""
    orphans = [_orphan() for _ in range(3)]
    db = _make_db(select_rows=orphans, update_rowcount=3)

    out = await recover_stuck_chats(db)

    assert out == 3
    insert_call = db.execute.await_args_list[1]
    marker_rows = insert_call.args[1]
    assert len(marker_rows) == 3
    # Every marker carries the interrupted-marker text — none stomped.
    for row, expected in zip(marker_rows, orphans, strict=True):
        assert row["message"] == CHAT_INTERRUPTED_MESSAGE
        assert row["session_id"] == expected.session_id


@pytest.mark.asyncio
async def test_preserves_design_id_for_design_section_orphans() -> None:
    """Design-section orphan → marker carries the same ``design_id``."""
    design_id = uuid.uuid4()
    orphan = _orphan(design_id=design_id)
    db = _make_db(select_rows=[orphan], update_rowcount=1)

    await recover_stuck_chats(db)

    insert_call = db.execute.await_args_list[1]
    marker_rows = insert_call.args[1]
    assert marker_rows[0]["design_id"] == design_id
