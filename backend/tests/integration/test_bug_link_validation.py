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

"""Bug link ids must name a BUD, feature or member of the caller's own org.

Filing a bug used to store whatever ``budId`` / ``featureId`` it was given,
so a bug could point at another org's BUD, a missing id crashed with a
foreign-key error, and a malformed id crashed while parsing.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1 import bugs as bugs_api
from app.core.security import create_access_token
from app.models.bud import BUDDocument, BUDStatus
from app.models.bug import Bug
from app.models.feature import Feature
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]
BUGS = "/api/v1/bugs"


@pytest.fixture(autouse=True)
def _no_embedding() -> Iterator[None]:
    """Keep the embedding model out: no background embed, no auto-link."""

    async def _no_link(*args: object) -> None:
        return None

    with (
        patch.object(bugs_api, "_schedule_embedding", lambda *a: None),
        patch.object(bugs_api, "embed_and_link_bug", _no_link),
    ):
        yield


async def _org(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    """An org with one manager; returns (org, manager, manager headers)."""
    async with factory() as db:
        org = Organization(name=f"Org {uuid.uuid4()}", slug=f"o-{uuid.uuid4().hex[:10]}")
        user = User(email=f"{uuid.uuid4().hex[:10]}@acme.dev", name="Mia", password_hash="x")
        db.add_all([org, user])
        await db.flush()
        role = await RoleRepository(db).get_by_name_system("manager")
        assert role is not None
        db.add(OrgToUser(user_id=user.id, org_id=org.id, role_id=role.id))
        await db.commit()
    token = create_access_token({"sub": str(user.id), "org_id": str(org.id)})
    return org.id, user.id, {"Authorization": f"Bearer {token}"}


async def _bud_and_feature(factory: Factory, org: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    async with factory() as db:
        bud = BUDDocument(org_id=org, bud_number=1, title="Theirs", status=BUDStatus.TESTING)
        feature = Feature(
            org_id=org, feature_title="Theirs", description="d", capabilities={},
            cluster_names=[], tags=[], cluster_signature=uuid.uuid4().hex,
        )  # fmt: skip
        db.add_all([bud, feature])
        await db.commit()
        return bud.id, feature.id


async def _bug_count(factory: Factory, org: uuid.UUID) -> int:
    async with factory() as db:
        rows = await db.execute(Bug.__table__.select().where(Bug.org_id == org))
        return len(rows.all())


async def _stored_assignee(factory: Factory, bug_id: uuid.UUID) -> uuid.UUID | None:
    """The bug's assignee as stored, read in a fresh session."""
    async with factory() as db:
        bug = await db.get(Bug, bug_id)
        assert bug is not None
        return bug.assignee_id


@pytest.mark.parametrize("field", ["budId", "featureId"])
async def test_filing_a_bug_against_another_orgs_bud_or_feature_is_refused(
    client: AsyncClient, pg_session_factory: Factory, field: str
) -> None:
    org, _, headers = await _org(pg_session_factory)
    other, _, _ = await _org(pg_session_factory)
    their_bud, their_feature = await _bud_and_feature(pg_session_factory, other)
    target = their_bud if field == "budId" else their_feature

    resp = await client.post(BUGS, json={"title": "x", field: str(target)}, headers=headers)

    assert resp.status_code == 404
    assert await _bug_count(pg_session_factory, org) == 0


async def test_filing_a_bug_against_a_missing_bud_is_not_found(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, _, headers = await _org(pg_session_factory)
    resp = await client.post(
        BUGS, json={"title": "x", "budId": str(uuid.uuid4())}, headers=headers
    )
    assert resp.status_code == 404
    assert await _bug_count(pg_session_factory, org) == 0


async def test_assigning_a_bug_to_someone_outside_the_org_is_refused(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _, me, headers = await _org(pg_session_factory)
    _, outsider, _ = await _org(pg_session_factory)
    bug_id = (await client.post(BUGS, json={"title": "x"}, headers=headers)).json()["id"]

    own = await client.patch(f"{BUGS}/{bug_id}", json={"assigneeId": str(me)}, headers=headers)
    assert own.status_code == 200 and own.json()["assigneeId"] == str(me)

    foreign = await client.patch(
        f"{BUGS}/{bug_id}", json={"assigneeId": str(outsider)}, headers=headers
    )
    assert foreign.status_code == 404
    assert await _stored_assignee(pg_session_factory, uuid.UUID(bug_id)) == me

    cleared = await client.patch(f"{BUGS}/{bug_id}", json={"assigneeId": None}, headers=headers)
    assert cleared.status_code == 200 and cleared.json()["assigneeId"] is None
    assert await _stored_assignee(pg_session_factory, uuid.UUID(bug_id)) is None


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "", {"title": "x", "budId": "not-a-uuid"}),
        ("post", "", {"title": "x", "featureId": "123"}),
        ("patch", "/{bug}", {"budId": "nope"}),
        ("patch", "/{bug}", {"assigneeId": "nope"}),
        ("get", "?budId=nope", None),
        ("get", "/board?featureId=nope", None),
        ("get", "/board?assigneeId=nope", None),
    ],
)
async def test_malformed_ids_are_rejected_as_invalid_input(
    client: AsyncClient,
    pg_session_factory: Factory,
    method: str,
    path: str,
    body: dict[str, str] | None,
) -> None:
    _, _, headers = await _org(pg_session_factory)
    bug_id = (await client.post(BUGS, json={"title": "x"}, headers=headers)).json()["id"]
    url = BUGS + path.format(bug=bug_id)

    resp = await client.request(method, url, json=body, headers=headers)

    assert resp.status_code == 422
