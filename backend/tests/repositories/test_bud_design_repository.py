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

"""Statement-shape tests for ``BUDDesignRepository.upsert``.

The upsert must be a single ``INSERT ... ON CONFLICT`` on the
``uq_bud_designs_bud_repo`` constraint, so concurrent callers serialize on
the unique index instead of racing a select-then-insert. The runtime
behaviour is covered by ``tests/integration/test_bud_design_upsert_concurrency.py``.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.repositories.bud import BUDDesignRepository


async def _rendered_upsert(**kwargs: str) -> str:
    """Run ``upsert`` against a mocked session and render the SQL it sent."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock())
    repo = BUDDesignRepository(db, org_id=uuid.uuid4())

    await repo.upsert(bud_id=uuid.uuid4(), repo_id=None, **kwargs)

    sent_stmt = db.execute.await_args.args[0]
    return str(sent_stmt.compile(dialect=postgresql.dialect()))


@pytest.mark.asyncio
async def test_design_upsert_targets_the_bud_repo_constraint() -> None:
    """The write is one ON CONFLICT statement on the (bud, repo) constraint."""
    rendered = await _rendered_upsert()

    assert rendered.startswith("INSERT INTO bud_designs")
    assert "ON CONFLICT ON CONSTRAINT uq_bud_designs_bud_repo DO UPDATE" in rendered
    assert "RETURNING" in rendered


@pytest.mark.asyncio
async def test_design_upsert_only_overwrites_fields_passed() -> None:
    """Omitted optional fields stay out of the UPDATE SET clause."""
    update_clause = (await _rendered_upsert(notes="n")).split("DO UPDATE SET", 1)[1]

    assert "notes =" in update_clause
    assert "status =" in update_clause
    assert "updated_at = now()" in update_clause
    assert "design_html =" not in update_clause
    assert "job_id =" not in update_clause
