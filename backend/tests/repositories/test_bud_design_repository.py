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

The upsert must be a single ``INSERT ... ON CONFLICT`` on the unique index
that matches the key (the partial ``uq_bud_designs_bud_level`` for the
BUD-level design, ``uq_bud_design_bud_repo`` for a repo design), so
concurrent callers serialize on it instead of racing a select-then-insert. The runtime
behaviour is covered by ``tests/integration/test_bud_design_upsert_concurrency.py``.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.repositories.bud import BUDDesignRepository


async def _rendered_upsert(repo_id: uuid.UUID | None = None, **kwargs: str) -> str:
    """Run ``upsert`` against a mocked session and render the SQL it sent."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock())
    repo = BUDDesignRepository(db, org_id=uuid.uuid4())

    await repo.upsert(bud_id=uuid.uuid4(), repo_id=repo_id, **kwargs)

    sent_stmt = db.execute.await_args.args[0]
    return str(sent_stmt.compile(dialect=postgresql.dialect()))


@pytest.mark.asyncio
async def test_bud_level_upsert_targets_the_partial_index() -> None:
    """repo_id NULL conflicts on the partial index over bud_id WHERE repo_id IS NULL."""
    rendered = await _rendered_upsert()

    assert rendered.startswith("INSERT INTO bud_designs")
    assert "ON CONFLICT (bud_id) WHERE repo_id IS NULL DO UPDATE" in rendered
    assert "RETURNING" in rendered


@pytest.mark.asyncio
async def test_repo_upsert_targets_the_bud_repo_constraint() -> None:
    """A repo design conflicts on the (bud, repo) unique constraint."""
    rendered = await _rendered_upsert(repo_id=uuid.uuid4())

    assert "ON CONFLICT ON CONSTRAINT uq_bud_design_bud_repo DO UPDATE" in rendered


@pytest.mark.asyncio
async def test_design_upsert_only_overwrites_fields_passed() -> None:
    """Omitted optional fields stay out of the UPDATE SET clause."""
    update_clause = (await _rendered_upsert(notes="n")).split("DO UPDATE SET", 1)[1]

    assert "notes =" in update_clause
    assert "status =" in update_clause
    assert "updated_at = now()" in update_clause
    assert "design_html =" not in update_clause
    assert "job_id =" not in update_clause


@pytest.mark.asyncio
async def test_design_upsert_raises_when_existing_row_is_another_orgs() -> None:
    """An empty RETURNING means the org guard skipped the update: raise, don't hide it."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    repo = BUDDesignRepository(db, org_id=uuid.uuid4())

    with pytest.raises(ValueError, match="belongs to another org"):
        await repo.upsert(bud_id=uuid.uuid4(), repo_id=None)
