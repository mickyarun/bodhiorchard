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

"""Editing a bug can't point it at another org, and follows the shared assignee rule.

A PATCH that relinks a bug to another org's BUD or feature is refused and
leaves the stored bug as it was. The assignee follows the same rule as BUDs
and todos: resending the stored assignee is a no-op even after they've
left, but once changed, someone outside the org can't be set again.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from app.models.bud import BUDDocument, BUDStatus
from app.models.bug import Bug
from app.models.feature import Feature
from app.models.user import OrgToUser
from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration

LINKS = {"budId": "bud_id", "featureId": "feature_id"}


@dataclass(frozen=True)
class _Org:
    org: uuid.UUID
    manager: uuid.UUID
    dev: uuid.UUID
    bud: uuid.UUID
    feature: uuid.UUID
    bug: uuid.UUID

    @property
    def headers(self) -> dict[str, str]:
        return as_user(self.manager, self.org)

    @property
    def path(self) -> str:
        return f"/api/v1/bugs/{self.bug}"


async def _org(factory: Factory) -> _Org:
    """An org with a manager, a developer, a BUD, a feature and a bug linked to both."""
    org, (manager, dev), _ = await setup_org(factory, "Mia", "Dev")
    await give_role(factory, org, manager, "manager")
    async with factory() as db:
        bud = BUDDocument(org_id=org, bud_number=1, title="Own", status=BUDStatus.TESTING)
        feature = Feature(
            org_id=org, feature_title="Own", description="d", capabilities={},
            cluster_names=[], tags=[], cluster_signature=uuid.uuid4().hex,
        )  # fmt: skip
        db.add_all([bud, feature])
        await db.flush()
        bug = Bug(
            org_id=org, bug_number=1, title="Export fails", reporter_id=manager,
            bud_id=bud.id, feature_id=feature.id,
        )  # fmt: skip
        db.add(bug)
        await db.commit()
        return _Org(org, manager, dev, bud.id, feature.id, bug.id)


async def _stored(factory: Factory, bug_id: uuid.UUID) -> Bug:
    """The bug as stored, read in a fresh session."""
    async with factory() as db:
        bug = await db.get(Bug, bug_id)
        assert bug is not None
        return bug


@pytest.mark.parametrize("field", sorted(LINKS))
async def test_relinking_a_bug_to_another_orgs_bud_or_feature_is_refused(
    client: AsyncClient, pg_session_factory: Factory, field: str
) -> None:
    a = await _org(pg_session_factory)
    b = await _org(pg_session_factory)
    target = b.bud if field == "budId" else b.feature

    resp = await client.patch(a.path, json={field: str(target)}, headers=a.headers)

    assert resp.status_code == 404, resp.text
    stored = await _stored(pg_session_factory, a.bug)
    assert (stored.bud_id, stored.feature_id) == (a.bud, a.feature)


async def test_resending_a_bug_assignee_who_left_is_a_no_op(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    a = await _org(pg_session_factory)
    given = await client.patch(a.path, json={"assigneeId": str(a.dev)}, headers=a.headers)
    assert given.status_code == 200, given.text
    async with pg_session_factory() as db:
        await db.execute(
            delete(OrgToUser).where(OrgToUser.user_id == a.dev, OrgToUser.org_id == a.org)
        )
        await db.commit()

    body = {"title": "Renamed", "assigneeId": str(a.dev)}
    edited = await client.patch(a.path, json=body, headers=a.headers)
    assert edited.status_code == 200, edited.text
    assert (await _stored(pg_session_factory, a.bug)).assignee_id == a.dev

    moved = await client.patch(a.path, json={"assigneeId": str(a.manager)}, headers=a.headers)
    assert moved.status_code == 200, moved.text
    back = await client.patch(a.path, json={"assigneeId": str(a.dev)}, headers=a.headers)
    assert back.status_code == 404, back.text
    assert (await _stored(pg_session_factory, a.bug)).assignee_id == a.manager
