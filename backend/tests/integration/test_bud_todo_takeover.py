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

"""``BUDTodoRepository.atomic_takeover`` across two open transactions.

The first session claims the TODO and holds its transaction open while the
second tries; once the first commits, the second must get ``None`` rather
than overwrite the holder. The outcome is the same whether the second
statement reaches the row lock before or after the commit, so the test has
no timing dependence.
"""

from __future__ import annotations

import asyncio

import pytest

from app.models.bud_todo import BUDTodoStatus
from app.repositories.bud_todo import BUDTodoRepository
from tests.integration.mcp_seed import (
    Factory,
    add_member,
    dev_bud_with_todo,
    get_todo,
    make_tenant,
)

pytestmark = pytest.mark.integration


async def test_second_transaction_loses_to_an_open_claim(pg_session_factory: Factory) -> None:
    """Session two's takeover returns None and the first holder is kept."""
    tenant = await make_tenant(pg_session_factory)
    bud_id = await dev_bud_with_todo(pg_session_factory, tenant)
    rival = await add_member(pg_session_factory, tenant.org_id, "Rival")

    async with pg_session_factory() as first, pg_session_factory() as second:
        claimed = await BUDTodoRepository(first, org_id=tenant.org_id).atomic_takeover(
            bud_id, 1, tenant.user_id
        )
        assert claimed is not None
        losing = asyncio.create_task(
            BUDTodoRepository(second, org_id=tenant.org_id).atomic_takeover(bud_id, 1, rival)
        )
        await first.commit()
        assert await asyncio.wait_for(losing, timeout=10) is None
        await second.commit()

    todo = await get_todo(pg_session_factory, bud_id, 1)
    assert (todo.status, todo.assignee_id) == (BUDTodoStatus.IN_PROGRESS.value, tenant.user_id)


async def test_takeover_scoped_to_another_org_claims_nothing(pg_session_factory: Factory) -> None:
    """A repository for a different org can't claim this org's TODO."""
    tenant = await make_tenant(pg_session_factory)
    other = await make_tenant(pg_session_factory)
    bud_id = await dev_bud_with_todo(pg_session_factory, tenant)

    async with pg_session_factory() as db:
        result = await BUDTodoRepository(db, org_id=other.org_id).atomic_takeover(
            bud_id, 1, other.user_id
        )
        await db.commit()

    assert result is None
    todo = await get_todo(pg_session_factory, bud_id, 1)
    assert (todo.status, todo.assignee_id) == (BUDTodoStatus.PENDING.value, None)
