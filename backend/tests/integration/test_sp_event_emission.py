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

"""Drive the REAL handlers and assert the SP/timeline side-effects fire.

Where ``test_sp_lifecycle`` stubs inputs to pin the award maths, this file
exercises the *emission* paths the maths depends on: the bug PATCH handler
(QA reject penalty / production-close reward), the MCP design-write handler
(``design_updated`` event), and the BUD PATCH handler (figma-link change →
``design_updated``). These are the wirings a unit test with mocks can't
prove actually record anything in a real request.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.responses import Response

from app.api.v1.bud import update_bud
from app.api.v1.bugs import update_bug
from app.mcp.auth import MCPAuthResult
from app.mcp.handlers_bud_design import handle_write_bud_design
from app.models.bud import BUDDocument, BUDStatus, BUDTimelineEvent
from app.models.bug import Bug, BugStatus, BugType
from app.models.developer_xp import RewardEvent, RewardType
from app.models.organization import Organization
from app.models.role import Role, RoleScopeType
from app.models.user import OrgToUser, User
from app.schemas.bud import BUDUpdate
from app.schemas.bug import BugUpdate

pytestmark = pytest.mark.integration


async def _seed_user(db: AsyncSession, org_id: uuid.UUID, *, role_name: str) -> User:
    """Create a user + role-scoped membership; return the User with org_id set.

    ``User`` has no ``org_id`` column — the auth dependency attaches it from
    the JWT membership at request time (``deps.get_current_user``). We mimic
    that so the handlers, called directly here, see the same shape.
    """
    user = User(
        email=f"{role_name}-{uuid.uuid4().hex[:6]}@example.com",
        name=role_name,
        password_hash="x",
    )
    db.add(user)
    await db.flush()
    role = (
        await db.execute(select(Role).where(Role.name == role_name, Role.org_id == org_id))
    ).scalar_one_or_none()
    if role is None:
        role = Role(name=role_name, org_id=org_id, scope_type=RoleScopeType.SYSTEM)
        db.add(role)
        await db.flush()
    db.add(OrgToUser(user_id=user.id, org_id=org_id, role_id=role.id))
    await db.flush()
    user.org_id = org_id  # type: ignore[attr-defined]
    return user


async def _new_org(db: AsyncSession) -> uuid.UUID:
    org = Organization(name=f"Emit {uuid.uuid4()}", slug=f"e-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()
    return org.id


async def _sp_ledger(
    factory: async_sessionmaker[AsyncSession], org_id: uuid.UUID
) -> dict[str, float]:
    async with factory() as db:
        rows = (
            (
                await db.execute(
                    select(RewardEvent).where(
                        RewardEvent.org_id == org_id, RewardEvent.type == RewardType.SP
                    )
                )
            )
            .scalars()
            .all()
        )
    return {r.source_ref: float(r.amount) for r in rows if r.source_ref}


async def _design_events(
    factory: async_sessionmaker[AsyncSession], bud_id: uuid.UUID
) -> list[BUDTimelineEvent]:
    async with factory() as db:
        rows = (
            (
                await db.execute(
                    select(BUDTimelineEvent).where(
                        BUDTimelineEvent.bud_id == bud_id,
                        BUDTimelineEvent.event_type == "design_updated",
                    )
                )
            )
            .scalars()
            .all()
        )
    return list(rows)


@pytest.mark.asyncio
async def test_bug_rejected_penalizes_qa_reporter(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    factory = pg_session_factory
    async with factory() as db:
        org_id = await _new_org(db)
        qa = await _seed_user(db, org_id, role_name="qa")
        bug = Bug(
            org_id=org_id,
            bug_number=1,
            title="prod bug",
            reporter_id=qa.id,
            bug_type=BugType.PRODUCTION,
            status=BugStatus.OPEN,
        )
        db.add(bug)
        await db.flush()
        bug_id = bug.id
        await db.commit()

    async with factory() as db:
        qa_user = await db.get(User, qa.id)
        qa_user.org_id = org_id  # type: ignore[attr-defined]
        await update_bug(bug_id, BugUpdate(status="rejected"), current_user=qa_user, db=db)
        await db.commit()

    async with factory() as db:
        refreshed = await db.get(Bug, bug_id)
        assert refreshed.rejected_at is not None
    assert (await _sp_ledger(factory, org_id)).get(f"sp_qa_rejected:{bug_id}") == -0.10


@pytest.mark.asyncio
async def test_production_bug_closed_rewards_qa_reporter(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    factory = pg_session_factory
    async with factory() as db:
        org_id = await _new_org(db)
        qa = await _seed_user(db, org_id, role_name="qa")
        bug = Bug(
            org_id=org_id,
            bug_number=1,
            title="prod bug",
            reporter_id=qa.id,
            bug_type=BugType.PRODUCTION,
            status=BugStatus.OPEN,
        )
        db.add(bug)
        await db.flush()
        bug_id = bug.id
        await db.commit()

    async with factory() as db:
        qa_user = await db.get(User, qa.id)
        qa_user.org_id = org_id  # type: ignore[attr-defined]
        await update_bug(bug_id, BugUpdate(status="closed"), current_user=qa_user, db=db)
        await db.commit()

    assert (await _sp_ledger(factory, org_id)).get(f"sp_qa_prod:{bug_id}") == 0.5


@pytest.mark.asyncio
async def test_mcp_design_write_records_design_updated(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    factory = pg_session_factory
    async with factory() as db:
        org_id = await _new_org(db)
        designer = await _seed_user(db, org_id, role_name="designer")
        bud = BUDDocument(org_id=org_id, bud_number=1, title="d", status=BUDStatus.DESIGN)
        db.add(bud)
        await db.flush()
        bud_id = bud.id
        await db.commit()

    async with factory() as db:
        org_obj = await db.get(Organization, org_id)
        des_user = await db.get(User, designer.id)
        auth = MCPAuthResult(org=org_obj, user=des_user)
        await handle_write_bud_design(db, auth, {"bud_id": str(bud_id), "html": "<div>x</div>"})

    events = await _design_events(factory, bud_id)
    assert len(events) == 1
    assert events[0].actor_id == designer.id
    assert (events[0].detail or {}).get("source") == "mcp"


@pytest.mark.asyncio
async def test_bud_figma_change_records_design_updated(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    factory = pg_session_factory
    async with factory() as db:
        org_id = await _new_org(db)
        designer = await _seed_user(db, org_id, role_name="designer")
        bud = BUDDocument(org_id=org_id, bud_number=1, title="d", status=BUDStatus.DESIGN)
        db.add(bud)
        await db.flush()
        bud_id = bud.id
        await db.commit()

    async with factory() as db:
        des_user = await db.get(User, designer.id)
        des_user.org_id = org_id  # type: ignore[attr-defined]
        await update_bud(
            bud_id,
            BUDUpdate(figma_url="https://figma.com/file/abc"),
            Response(),
            current_user=des_user,
            db=db,
        )
        await db.commit()

    events = await _design_events(factory, bud_id)
    assert len(events) == 1
    assert (events[0].detail or {}).get("source") == "figma_url"
