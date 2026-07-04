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

"""Integration coverage for ``BUDTodoRepository.create_todo``.

Backs the manual "add todo" REST endpoint and the ``create_todo`` MCP tool.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bud import BUDDocument, BUDStatus
from app.models.bud_todo import BUDTodoStatus
from app.models.organization import Organization
from app.repositories.bud_todo import BUDTodoRepository


async def _bud(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    org = Organization(name=f"Todo {uuid.uuid4()}", slug=f"td-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()
    bud = BUDDocument(
        org_id=org.id, bud_number=1, title="Add products below 1GBP", status=BUDStatus.DEVELOPMENT
    )
    db.add(bud)
    await db.flush()
    return org.id, bud.id


async def test_create_todo_assigns_next_sequence_and_marks_manual(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as db:
        org_id, bud_id = await _bud(db)
        repo = BUDTodoRepository(db, org_id=org_id)

        first = await repo.create_todo(bud_id, title="Wire the endpoint", phase="development")
        assert first.sequence == 1
        assert first.status == BUDTodoStatus.PENDING.value
        assert first.is_checkpoint is False
        assert first.assignee_id is None

        second = await repo.create_todo(
            bud_id,
            title="Add a test",
            phase="development",
            description="cover the happy path",
            detail={"source": "manual"},
        )
        assert second.sequence == 2
        assert second.description == "cover the happy path"
        assert second.detail == {"source": "manual"}


async def test_next_sequence_continues_past_existing_todos(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as db:
        org_id, bud_id = await _bud(db)
        repo = BUDTodoRepository(db, org_id=org_id)

        # Two pre-existing rows (as the tech-spec parser would create).
        await repo.create_todo(bud_id, title="one", phase="development")
        await repo.create_todo(bud_id, title="two", phase="development")

        assert await repo.next_sequence(bud_id) == 3
        added = await repo.create_todo(bud_id, title="three", phase="development")
        assert added.sequence == 3
