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

"""Statement-shape tests for the BUD design row-level lock.

These verify ``BUDDesignRepository.upsert`` issues ``SELECT ... FOR UPDATE``
so concurrent ``upsert`` calls serialize at the DB row level — closes
the read→MCP-write window the previous in-process ``asyncio.Lock``
could not cover across workers.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.bud import BUDDesignRepository


@pytest.mark.asyncio
async def test_design_upsert_select_uses_for_update() -> None:
    """The select in ``upsert`` must carry the ``FOR UPDATE`` lock."""
    db = MagicMock()
    result_obj = MagicMock()
    result_obj.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result_obj)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()

    repo = BUDDesignRepository(db, org_id=uuid.uuid4())

    await repo.upsert(
        bud_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
    )

    sent_stmt = db.execute.await_args.args[0]
    rendered = str(sent_stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "FOR UPDATE" in rendered.upper()
