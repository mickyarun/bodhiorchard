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

"""Shared setup for the XP, SP, game and quiz integration tests.

Every helper creates fresh rows (new org, new users) so tests can share the
session database without seeing each other's points.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models.developer_xp import DeveloperXP, RewardEvent, RewardType
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from tests.integration.leave_support import Factory, give_role

BRIDGE_SECRET = "test-bridge-secret"


async def make_org(
    factory: Factory, *names: str, role: str | None = "developer"
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """A new org whose members (one per name) hold ``role`` (engineering access)."""
    async with factory() as db:
        org = Organization(name=f"Game {uuid.uuid4()}", slug=f"game-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        ids = []
        for name in names:
            user = User(
                email=f"{name.lower()}-{uuid.uuid4().hex[:6]}@acme.dev",
                name=name,
                password_hash="x",
            )
            db.add(user)
            await db.flush()
            db.add(OrgToUser(user_id=user.id, org_id=org.id))
            ids.append(user.id)
        await db.commit()
    if role:
        for user_id in ids:
            await give_role(factory, org.id, user_id, role)
    return org.id, ids


async def join_org(factory: Factory, org: uuid.UUID, user: uuid.UUID) -> None:
    """Add an existing user as a member of another org."""
    async with factory() as db:
        db.add(OrgToUser(user_id=user, org_id=org))
        await db.commit()


async def xp_row(factory: Factory, org: uuid.UUID, user: uuid.UUID) -> DeveloperXP | None:
    """The user's aggregate XP/SP row in ``org`` (None if never awarded)."""
    async with factory() as db:
        result = await db.execute(
            select(DeveloperXP).where(DeveloperXP.org_id == org, DeveloperXP.user_id == user)
        )
        return result.scalar_one_or_none()


async def events(
    factory: Factory, org: uuid.UUID, user: uuid.UUID, kind: RewardType | None = None
) -> list[RewardEvent]:
    """Every reward event for ``user`` in ``org`` (optionally one currency)."""
    async with factory() as db:
        stmt = select(RewardEvent).where(RewardEvent.org_id == org, RewardEvent.user_id == user)
        if kind is not None:
            stmt = stmt.where(RewardEvent.type == kind)
        return list((await db.execute(stmt)).scalars().all())


async def org_reward_count(factory: Factory, org: uuid.UUID) -> tuple[int, int]:
    """``(developer_xp rows, reward_events rows)`` for a whole org."""
    async with factory() as db:
        xp = await db.scalar(select(func.count()).where(DeveloperXP.org_id == org))
        ev = await db.scalar(select(func.count()).where(RewardEvent.org_id == org))
        return int(xp or 0), int(ev or 0)


def capture_publish(monkeypatch: pytest.MonkeyPatch, module: Any) -> list[tuple[str, Any]]:
    """Replace ``module.publish`` with a recorder and return the list it fills."""
    sent: list[tuple[str, Any]] = []
    monkeypatch.setattr(module, "publish", lambda topic, payload: sent.append((topic, payload)))
    return sent


def bridge(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Configure a known bridge secret and return the header that carries it."""
    monkeypatch.setattr(settings.colyseus, "bridge_secret", BRIDGE_SECRET)
    return {"X-Bridge-Secret": BRIDGE_SECRET}
