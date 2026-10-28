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

"""The triage approval queue: approve creates exactly one BUD, reject closes the ask.

Slack, the agent task trigger, phase auto-assignment and the embedding
model are faked; the BUD, planned feature and session rows are real.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.bud import BUDDocument, BUDPriority
from app.repositories.feature import FeatureRepository
from tests.integration.scan_features_bugs_support import Factory, as_user, new_member, new_org
from tests.integration.triage_support import TriageFakes, new_session

pytestmark = pytest.mark.integration

TRIAGE = "/api/v1/triage-sessions"


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> TriageFakes:
    """Swap Slack, agents, assignment and embeddings for recorders."""
    return TriageFakes.install(monkeypatch)


async def _pm(factory: Factory, **org_cols: object) -> tuple[uuid.UUID, dict[str, str]]:
    org = await new_org(factory, **org_cols)
    return org, as_user(await new_member(factory, org, "pm"), org)


async def _bud_count(factory: Factory, org: uuid.UUID) -> int:
    async with factory() as db:
        count = await db.scalar(
            select(func.count()).select_from(BUDDocument).where(BUDDocument.org_id == org)
        )
        return int(count or 0)


async def test_approving_creates_one_bud_with_a_planned_feature_and_tells_slack(
    client: AsyncClient, pg_session_factory: Factory, fakes: TriageFakes
) -> None:
    org, headers = await _pm(pg_session_factory, slack_bot_token="xoxb-test")
    session = await new_session(
        pg_session_factory, org, priority="P0", name="Saved carts", thread="111.222"
    )

    resp = await client.post(f"{TRIAGE}/{session}/approve", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "bud_created" and body["bud_id"] is not None
    async with pg_session_factory() as db:
        bud = await db.get(BUDDocument, uuid.UUID(body["bud_id"]))
        features = FeatureRepository(db, org_id=org)
        feature = await features.get_by_source_ref("BUD-001", source="bud")
    assert bud is not None and bud.bud_number == 1 and bud.title == "Saved carts"
    assert bud.priority == BUDPriority.P0
    assert bud.embedding is not None
    assert bud.metadata_ == {"source": "slack_triage", "triage_session_id": str(session)}
    assert feature is not None and feature.feature_status == "planned"
    assert fakes.slack == [("xoxb-test", "C1", "BUD-001", "111.222")]
    assert fakes.agent_tasks == [(bud.id, "bud", True)]


async def test_approving_without_a_slack_bot_still_creates_the_bud(
    client: AsyncClient, pg_session_factory: Factory, fakes: TriageFakes
) -> None:
    org, headers = await _pm(pg_session_factory)
    session = await new_session(pg_session_factory, org)
    resp = await client.post(f"{TRIAGE}/{session}/approve", headers=headers)
    assert resp.status_code == 200
    assert fakes.slack == []
    assert await _bud_count(pg_session_factory, org) == 1


async def test_a_session_is_decided_only_once(
    client: AsyncClient, pg_session_factory: Factory, fakes: TriageFakes
) -> None:
    org, headers = await _pm(pg_session_factory)
    approved = await new_session(pg_session_factory, org)
    rejected = await new_session(pg_session_factory, org)

    await client.post(f"{TRIAGE}/{approved}/approve", headers=headers)
    await client.post(f"{TRIAGE}/{rejected}/reject", headers=headers)

    for sid in (approved, rejected):
        for action in ("approve", "reject"):
            again = await client.post(f"{TRIAGE}/{sid}/{action}", headers=headers)
            assert again.status_code == 409
    assert await _bud_count(pg_session_factory, org) == 1
    assert len(fakes.agent_tasks) == 1


async def test_rejecting_closes_the_session_and_posts_to_its_thread(
    client: AsyncClient, pg_session_factory: Factory, fakes: TriageFakes
) -> None:
    org, headers = await _pm(pg_session_factory, slack_bot_token="xoxb-test")
    session = await new_session(pg_session_factory, org, thread="111.222")

    resp = await client.post(f"{TRIAGE}/{session}/reject", headers=headers)

    assert resp.status_code == 200 and resp.json()["status"] == "rejected"
    assert resp.json()["bud_id"] is None
    assert [(c, t) for _, c, _, t in fakes.slack] == [("C1", "111.222")]
    assert await _bud_count(pg_session_factory, org) == 0


async def test_another_orgs_session_cannot_be_seen_or_decided(
    client: AsyncClient, pg_session_factory: Factory, fakes: TriageFakes
) -> None:
    org_a, _ = await _pm(pg_session_factory)
    org_b, outsider = await _pm(pg_session_factory)
    session = await new_session(pg_session_factory, org_a)

    listed = await client.get(f"{TRIAGE}/", headers=outsider)
    approve = await client.post(f"{TRIAGE}/{session}/approve", headers=outsider)
    reject = await client.post(f"{TRIAGE}/{session}/reject", headers=outsider)

    assert listed.json() == []
    assert approve.status_code == 404 and reject.status_code == 404
    assert await _bud_count(pg_session_factory, org_a) == 0
    assert await _bud_count(pg_session_factory, org_b) == 0


async def test_the_queue_lists_waiting_sessions_by_default_and_filters_by_status(
    client: AsyncClient, pg_session_factory: Factory, fakes: TriageFakes
) -> None:
    org, headers = await _pm(pg_session_factory)
    waiting = await new_session(pg_session_factory, org)
    await new_session(pg_session_factory, org, status="interviewing")

    default = (await client.get(f"{TRIAGE}/", headers=headers)).json()
    interviewing = (await client.get(f"{TRIAGE}/?status=interviewing", headers=headers)).json()
    bad = await client.get(f"{TRIAGE}/?status=pending", headers=headers)

    assert [s["id"] for s in default] == [str(waiting)]
    assert [s["status"] for s in interviewing] == ["interviewing"]
    assert bad.status_code == 400


async def test_only_backlog_approvers_reach_the_queue(
    client: AsyncClient, pg_session_factory: Factory, fakes: TriageFakes
) -> None:
    org = await new_org(pg_session_factory)
    dev = as_user(await new_member(pg_session_factory, org, "developer"), org)
    session = await new_session(pg_session_factory, org)

    assert (await client.get(f"{TRIAGE}/", headers=dev)).status_code == 403
    assert (await client.post(f"{TRIAGE}/{session}/approve", headers=dev)).status_code == 403
    assert await _bud_count(pg_session_factory, org) == 0


async def test_an_unknown_session_is_not_found(
    client: AsyncClient, pg_session_factory: Factory, fakes: TriageFakes
) -> None:
    _, headers = await _pm(pg_session_factory)
    resp = await client.post(f"{TRIAGE}/{uuid.uuid4()}/approve", headers=headers)
    assert resp.status_code == 404
