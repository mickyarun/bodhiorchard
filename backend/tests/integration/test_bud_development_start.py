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

"""PATCH into development crystallises the plan.

The tech spec's Implementation TODO section becomes BUDTodo rows, the
BUD goes to a developer, its todos follow, and the PERT re-estimate is
deferred until after the commit. Coming back into development later
re-syncs without duplicating the todos.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.bud import BUDStatus
from app.models.bud_todo import BUDTodo
from tests.integration.bud_lifecycle_reads import load_bud, timeline
from tests.integration.bud_lifecycle_support import (
    Factory,
    add_bud,
    add_member,
    as_user,
    new_org,
    stub_externals,
)
from tests.integration.bud_lifecycle_support import (
    app_database_blocked as app_database_blocked,
)

pytestmark = pytest.mark.integration

SPEC = "# Spec\n\n## Implementation TODO\n\n1. Add retry table\n2. Wire the retry worker\n"


async def _todos(factory: Factory, bud_id: uuid.UUID) -> list[BUDTodo]:
    """The BUD's todos in sequence order."""
    async with factory() as db:
        rows = await db.scalars(
            select(BUDTodo).where(BUDTodo.bud_id == bud_id).order_by(BUDTodo.sequence)
        )
        return list(rows)


async def _setup(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    """Org with one developer, a tech_arch BUD carrying ``SPEC``; PM headers."""
    org = await new_org(factory)
    pm = await add_member(factory, org, "pm")
    dev = await add_member(factory, org, "dev", role="developer")
    bud_id = await add_bud(factory, org, status=BUDStatus.TECH_ARCH, tech_spec_md=SPEC)
    return dev, bud_id, as_user(pm, org)


async def test_entering_development_syncs_assigns_and_defers_the_estimate(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Two todos from the spec, both on the developer lead; estimator scheduled once."""
    dev, bud_id, headers = await _setup(pg_session_factory)

    with stub_externals() as ext:
        res = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"status": "development"}, headers=headers
        )

    assert res.status_code == 200
    assert (await load_bud(pg_session_factory, bud_id)).assignee_id == dev
    todos = await _todos(pg_session_factory, bud_id)
    assert [(t.sequence, t.title) for t in todos] == [
        (1, "Add retry table"),
        (2, "Wire the retry worker"),
    ]
    assert {t.assignee_id for t in todos} == {dev}
    assert ext.dev_estimate.call_count == 1
    assert ext.dev_estimate.call_args.kwargs["bud_id"] == bud_id
    assert await timeline(pg_session_factory, bud_id, "status_change") == [
        {"from": "tech_arch", "to": "development"}
    ]


async def test_returning_to_development_does_not_duplicate_todos(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """development -> code_review -> development keeps the same two todos."""
    _dev, bud_id, headers = await _setup(pg_session_factory)
    url = f"/api/v1/buds/{bud_id}"

    with stub_externals() as ext:
        for target in ("development", "code_review", "development"):
            res = await client.patch(url, json={"status": target}, headers=headers)
            assert res.status_code == 200

    assert [t.sequence for t in await _todos(pg_session_factory, bud_id)] == [1, 2]
    assert ext.dev_estimate.call_count == 2


async def test_spec_without_todo_section_starts_development_with_no_todos(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """No Implementation TODO section: the move still succeeds, nothing is synced."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    bud_id = await add_bud(
        pg_session_factory, org, status=BUDStatus.TECH_ARCH, tech_spec_md="# Spec\n\nNo plan."
    )

    with stub_externals():
        res = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"status": "development"}, headers=as_user(pm, org)
        )

    assert res.status_code == 200
    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.DEVELOPMENT
    assert await _todos(pg_session_factory, bud_id) == []
