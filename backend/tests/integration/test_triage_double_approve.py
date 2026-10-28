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

"""Two people deciding the same triage session at once.

Both requests used to read the session as still waiting; the slower one
then failed on the BUD-number unique key with a 500 instead of being told
the session was already decided.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1 import triage_sessions as triage_api
from app.core.security import create_access_token
from app.models.bud import BUDDocument
from app.models.organization import Organization
from app.models.triage_session import TriageSession, TriageStatus
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository
from app.services import feature_lifecycle

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]


@pytest.fixture(autouse=True)
def _quiet_outside_world(monkeypatch: pytest.MonkeyPatch) -> None:
    """No agents, assignment, Slack or embedding model."""

    async def _nothing(*args: Any, **kwargs: Any) -> None:
        return None

    async def _embed(text: str) -> list[float]:
        return [1.0] + [0.0] * 383

    embedder = SimpleNamespace(embed=_embed)
    monkeypatch.setattr(triage_api, "create_agent_task_for_stage", _nothing)
    monkeypatch.setattr(triage_api, "auto_assign_for_phase", _nothing)
    monkeypatch.setattr(triage_api, "embedding_service", embedder)
    monkeypatch.setattr(feature_lifecycle, "embedding_service", embedder)


async def _waiting_session(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    """An org, a PM's headers and one session awaiting approval."""
    async with factory() as db:
        org = Organization(name=f"Org {uuid.uuid4()}", slug=f"o-{uuid.uuid4().hex[:10]}")
        user = User(email=f"{uuid.uuid4().hex[:10]}@acme.dev", name="Pat", password_hash="x")
        db.add_all([org, user])
        await db.flush()
        role = await RoleRepository(db).get_by_name_system("pm")
        assert role is not None
        db.add(OrgToUser(user_id=user.id, org_id=org.id, role_id=role.id))
        session = TriageSession(
            org_id=org.id,
            slack_channel="C1",
            thread_ts="1.1",
            original_msg_ts="1.1",
            requester_slack_id="U1",
            status=TriageStatus.AWAITING_PM,
            feature_name="Saved carts",
        )
        db.add(session)
        await db.commit()
    token = create_access_token({"sub": str(user.id), "org_id": str(org.id)})
    return org.id, session.id, {"Authorization": f"Bearer {token}"}


async def _outcome(client: AsyncClient, url: str, headers: dict[str, str]) -> int | str:
    try:
        return (await client.post(url, headers=headers)).status_code
    except Exception as exc:  # an unhandled server error surfaces through the transport
        return type(exc).__name__


@pytest.mark.parametrize("second", ["approve", "reject"])
async def test_a_concurrent_second_decision_is_told_the_session_is_taken(
    client: AsyncClient, pg_session_factory: Factory, second: str
) -> None:
    org, session, headers = await _waiting_session(pg_session_factory)
    base = f"/api/v1/triage-sessions/{session}"

    approve, other = await asyncio.gather(
        _outcome(client, f"{base}/approve", headers),
        _outcome(client, f"{base}/{second}", headers),
    )

    assert sorted([approve, other], key=str) == [200, 409]
    async with pg_session_factory() as db:
        buds = await db.scalar(
            select(func.count()).select_from(BUDDocument).where(BUDDocument.org_id == org)
        )
        decided = await db.get(TriageSession, session)
    approved = approve == 200
    assert buds == (1 if approved else 0)
    assert decided is not None
    assert decided.status == (TriageStatus.BUD_CREATED if approved else TriageStatus.REJECTED)
