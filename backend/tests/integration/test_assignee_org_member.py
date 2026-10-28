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

"""A BUD or TODO can only be assigned to a member of its own org.

Assigning another org's member used to succeed and echo their name back
into the caller's org; an id that matched no user was a 500.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from app.models.base import BaseModel
from app.models.bud import BUDDocument, BUDStatus
from app.models.bud_todo import BUDTodo
from app.models.user import OrgToUser
from app.repositories.bud_todo import BUDTodoRepository
from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class _Org:
    org: uuid.UUID
    owner: uuid.UUID
    dev: uuid.UUID
    bud: uuid.UUID
    todo: uuid.UUID


@dataclass(frozen=True)
class _Route:
    """How to set the assignee on one kind of row."""

    model: type[BaseModel]
    key: str

    def path(self, o: _Org) -> str:
        if self.model is BUDDocument:
            return f"/api/v1/buds/{o.bud}"
        return f"/api/v1/buds/{o.bud}/todos/{o.todo}"

    def row(self, o: _Org) -> uuid.UUID:
        return o.bud if self.model is BUDDocument else o.todo


ROUTES = {
    "bud": _Route(BUDDocument, "assignee_id"),
    "todo": _Route(BUDTodo, "assigneeId"),
}


async def _org(factory: Factory) -> _Org:
    org, (owner, dev), _ = await setup_org(factory, "Owner", "Dev")
    await give_role(factory, org, owner, "org_owner")
    async with factory() as db:
        bud = BUDDocument(org_id=org, bud_number=1, title="Own BUD", status=BUDStatus.DEVELOPMENT)
        db.add(bud)
        await db.flush()
        todo = await BUDTodoRepository(db, org_id=org).create_todo(
            bud.id, title="Own todo", phase="development"
        )
        await db.commit()
        return _Org(org, owner, dev, bud.id, todo.id)


async def _assignee(factory: Factory, route: _Route, o: _Org) -> uuid.UUID | None:
    async with factory() as db:
        row = await db.get(route.model, route.row(o))
        assert row is not None
        value: uuid.UUID | None = row.assignee_id  # type: ignore[attr-defined]
        return value


@pytest.mark.parametrize("name", sorted(ROUTES))
async def test_only_a_member_of_the_org_can_be_assigned(
    client: AsyncClient, pg_session_factory: Factory, name: str
) -> None:
    route = ROUTES[name]
    a = await _org(pg_session_factory)
    b = await _org(pg_session_factory)
    headers = as_user(a.owner, a.org)
    for stranger in (b.dev, uuid.uuid4()):  # another org's member; no user at all
        refused = await client.patch(
            route.path(a), json={route.key: str(stranger)}, headers=headers
        )
        assert refused.status_code == 404, refused.text
        assert refused.json() == {"detail": "Assignee not found"}
        assert await _assignee(pg_session_factory, route, a) is None

    own = await client.patch(route.path(a), json={route.key: str(a.dev)}, headers=headers)
    assert own.status_code == 200, own.text
    assert await _assignee(pg_session_factory, route, a) == a.dev


@pytest.mark.parametrize("name", sorted(ROUTES))
async def test_resending_an_assignee_who_left_does_not_block_other_edits(
    client: AsyncClient, pg_session_factory: Factory, name: str
) -> None:
    route = ROUTES[name]
    a = await _org(pg_session_factory)
    headers = as_user(a.owner, a.org)
    given = await client.patch(route.path(a), json={route.key: str(a.dev)}, headers=headers)
    assert given.status_code == 200, given.text
    async with pg_session_factory() as db:
        await db.execute(
            delete(OrgToUser).where(OrgToUser.user_id == a.dev, OrgToUser.org_id == a.org)
        )
        await db.commit()

    body = {"title": "Renamed", route.key: str(a.dev)}
    edited = await client.patch(route.path(a), json=body, headers=headers)
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "Renamed"
