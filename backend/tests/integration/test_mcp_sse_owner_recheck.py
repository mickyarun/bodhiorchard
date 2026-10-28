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

"""The ``GET /mcp/sse`` heartbeat drops the stream when the token's owner loses access.

Each beat re-checked only the token row, so an owner who was deactivated,
removed from the org or moved to a role without engineering access kept an
open stream as long as the row survived — although every POST call from the
same token was refused. The route is called directly; the token, the owner
and the org are real rows.
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request
from starlette.types import Message

from app.core.security import hash_password
from app.mcp import streamable
from app.mcp.auth import MCPAuthResult, compute_token_prefix
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.models.user_mcp_token import UserMCPToken
from app.repositories.role import RoleRepository
from app.services.permission_seeder import seed_permissions

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]
PING = b": ping\n\n"


@dataclass(frozen=True)
class Owner:
    """A developer with a per-user MCP token."""

    org: Organization
    user_id: uuid.UUID
    membership_id: uuid.UUID
    token_id: uuid.UUID


async def _owner(factory: Factory) -> Owner:
    tag = uuid.uuid4().hex[:8]
    async with factory() as db:
        await seed_permissions(db)
        org = Organization(name=f"Acme {tag}", slug=f"acme-{tag}", config={})
        user = User(email=f"dev-{tag}@example.test", name="dev", password_hash="x")
        db.add_all([org, user])
        await db.flush()
        role = await RoleRepository(db).get_by_name_system("developer")
        assert role is not None
        plaintext = secrets.token_urlsafe(32)
        token = UserMCPToken(
            user_id=user.id,
            org_id=org.id,
            name="desktop",
            token_hash=hash_password(plaintext),
            token_prefix=compute_token_prefix(plaintext),
        )
        membership = OrgToUser(user_id=user.id, org_id=org.id, role_id=role.id)
        db.add_all([membership, token])
        await db.commit()
        return Owner(org, user.id, membership.id, token.id)


async def _body(owner: Owner, limit: int = 4) -> bytes:
    """Up to ``limit`` chunks of the stream (an open stream is cut off there)."""

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(
        {"type": "http", "method": "GET", "path": "/mcp/sse", "headers": []}, receive
    )
    response = await streamable.remote_mcp_sse(
        request, MCPAuthResult(org=owner.org, token_id=owner.token_id)
    )
    iterator = response.body_iterator
    chunks: list[bytes] = []

    async def collect() -> None:
        async for chunk in iterator:
            chunks.append(chunk.encode() if isinstance(chunk, str) else bytes(chunk))
            if len(chunks) >= limit:
                break

    try:
        await asyncio.wait_for(collect(), 5)
    finally:
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()
    return b"".join(chunks)


@pytest.fixture
def fast_beats(pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Heartbeat at once, with the stream's own sessions on the test database."""
    monkeypatch.setattr(streamable, "AsyncSessionLocal", pg_session_factory)
    monkeypatch.setattr(streamable, "_SSE_HEARTBEAT_SECONDS", 0)


@pytest.mark.usefixtures("fast_beats")
async def test_active_owner_keeps_the_stream(pg_session_factory: Factory) -> None:
    owner = await _owner(pg_session_factory)
    assert (await _body(owner)).count(PING) == 3


@pytest.mark.usefixtures("fast_beats")
async def test_deactivated_owner_loses_the_stream(pg_session_factory: Factory) -> None:
    owner = await _owner(pg_session_factory)
    async with pg_session_factory() as db:
        user = await db.get(User, owner.user_id)
        assert user is not None
        user.is_active = False
        await db.commit()

    assert (await _body(owner)).count(PING) == 0


@pytest.mark.usefixtures("fast_beats")
async def test_owner_removed_from_the_org_loses_the_stream(pg_session_factory: Factory) -> None:
    owner = await _owner(pg_session_factory)
    async with pg_session_factory() as db:
        membership = await db.get(OrgToUser, owner.membership_id)
        assert membership is not None
        await db.delete(membership)
        await db.commit()

    assert (await _body(owner)).count(PING) == 0


@pytest.mark.usefixtures("fast_beats")
async def test_owner_without_engineering_access_loses_the_stream(
    pg_session_factory: Factory,
) -> None:
    owner = await _owner(pg_session_factory)
    async with pg_session_factory() as db:
        membership = await db.get(OrgToUser, owner.membership_id)
        hr = await RoleRepository(db).get_by_name_system("hr")
        assert membership is not None and hr is not None
        membership.role_id = hr.id
        await db.commit()

    assert (await _body(owner)).count(PING) == 0
