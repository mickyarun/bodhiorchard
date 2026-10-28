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

"""Concurrent ``PATCH /buds/{id}`` requests on one BUD serialise.

Two simultaneous closes: one wins, the other sees a closed BUD and gets
the normal 400, and the close side effects run once. Two simultaneous
edits: both succeed and history gets two consecutive versions instead
of one request failing on the version number. The version number is
also safe for every other history writer (revert, chat, agents, MCP),
which all go through ``commit_snapshot``.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import create_access_token
from app.models.bud import BUDDocument, BUDStatus, BUDTimelineEvent
from app.models.bud_version import BUDEditSource, BUDVersion
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.repositories import bud_version as bud_version_repo
from app.repositories.role import RoleRepository

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]


async def _bud_and_pm(factory: Factory, status: BUDStatus) -> tuple[uuid.UUID, dict[str, str]]:
    """A fresh org with one PM and one BUD in ``status``; returns (bud id, headers)."""
    async with factory() as db:
        org = Organization(name=f"Lock {uuid.uuid4()}", slug=f"lock-{uuid.uuid4().hex[:10]}")
        user = User(email=f"pm-{uuid.uuid4().hex[:8]}@example.com", name="pm", password_hash="x")
        db.add_all([org, user])
        await db.flush()
        role = await RoleRepository(db).get_by_name_system("pm")
        assert role is not None
        db.add(OrgToUser(user_id=user.id, org_id=org.id, role_id=role.id))
        bud = BUDDocument(org_id=org.id, bud_number=1, title="t0", status=status)
        db.add(bud)
        await db.commit()
        token = create_access_token({"sub": str(user.id), "org_id": str(org.id)})
        return bud.id, {"Authorization": f"Bearer {token}"}


async def test_concurrent_closes_close_once(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """One 200 and one 400; a single status change and a single closure run."""
    bud_id, headers = await _bud_and_pm(pg_session_factory, BUDStatus.UAT)
    closure = AsyncMock()

    with patch("app.services.bud_closure.on_bud_closed", closure):
        responses = await asyncio.gather(
            *(
                client.patch(f"/api/v1/buds/{bud_id}", json={"status": "closed"}, headers=headers)
                for _ in range(2)
            )
        )

    assert sorted(r.status_code for r in responses) == [200, 400]
    assert closure.await_count == 1
    async with pg_session_factory() as db:
        changes = list(
            await db.scalars(
                select(BUDTimelineEvent.detail).where(
                    BUDTimelineEvent.bud_id == bud_id,
                    BUDTimelineEvent.event_type == "status_change",
                )
            )
        )
    assert changes == [{"from": "uat", "to": "closed"}]


async def test_concurrent_edits_both_land_in_history(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Two simultaneous title edits: both 200, versions 1 and 2."""
    bud_id, headers = await _bud_and_pm(pg_session_factory, BUDStatus.BUD)

    responses = await asyncio.gather(
        *(
            client.patch(f"/api/v1/buds/{bud_id}", json={"title": f"t{i}"}, headers=headers)
            for i in (1, 2)
        )
    )

    assert [r.status_code for r in responses] == [200, 200]
    async with pg_session_factory() as db:
        versions = list(
            await db.scalars(select(BUDVersion.version_no).where(BUDVersion.bud_id == bud_id))
        )
    assert sorted(versions) == [1, 2]


async def _wait_until_blocked(factory: Factory, bud_id: uuid.UUID) -> None:
    """Return once some other session is waiting on a lock (bounded poll)."""
    probe = text(
        "SELECT count(*) FROM pg_stat_activity "
        "WHERE wait_event_type = 'Lock' AND datname = current_database()"
    )
    async with factory() as db:
        for _ in range(500):
            if await db.scalar(probe):
                return
            await asyncio.sleep(0.01)
    raise AssertionError(f"second writer on {bud_id} never reached the database")


async def test_concurrent_history_writers_get_consecutive_versions(
    pg_session_factory: Factory,
) -> None:
    """A second writer snapshotting while the first is uncommitted gets version 2."""
    bud_id, _headers = await _bud_and_pm(pg_session_factory, BUDStatus.BUD)

    async def _snapshot(db: AsyncSession, source: BUDEditSource) -> None:
        """Snapshot the BUD's current state into the bud phase."""
        bud = await db.get(BUDDocument, bud_id)
        assert bud is not None
        await bud_version_repo.insert_snapshot(
            db, bud=bud, phase=BUDStatus.BUD, source=source, edited_by=None
        )

    async def _second_writer() -> None:
        """The MCP-style writer, in its own transaction."""
        async with pg_session_factory() as db:
            await _snapshot(db, BUDEditSource.MCP)
            await db.commit()

    async with pg_session_factory() as first:
        await _snapshot(first, BUDEditSource.AGENT)
        second = asyncio.create_task(_second_writer())
        await _wait_until_blocked(pg_session_factory, bud_id)
        await first.commit()
    await second

    async with pg_session_factory() as db:
        versions = list(
            await db.scalars(select(BUDVersion.version_no).where(BUDVersion.bud_id == bud_id))
        )
    assert sorted(versions) == [1, 2]
