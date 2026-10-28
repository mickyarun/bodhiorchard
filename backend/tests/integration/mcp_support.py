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

"""Shared setup for the MCP integration tests.

Every tenant is a fresh org with one member holding a real per-user MCP
token (bcrypt-hashed, prefix-indexed, exactly as the settings endpoint
mints them). Tests call ``/mcp/tools/{name}`` through the real router, so
token verification, dispatch and the handlers all run against Postgres.

:func:`isolate_side_channels` points the audit writer and the token
``last_used_at`` toucher at the test database, turns rate limiting off
(no redis) and replaces the embedding model with a fixed vector, so no
test reaches the developer's database, redis or the ONNX model download.
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import hash_password
from app.mcp import audit as mcp_audit
from app.mcp import auth as mcp_auth
from app.mcp import rate_limit as mcp_rate_limit
from app.mcp.auth import compute_token_prefix
from app.models.bud import BUDDocument, BUDStatus
from app.models.bud_todo import BUDTodo
from app.models.mcp_audit_log import MCPAuditLogEntry
from app.models.organization import Organization
from app.models.tracked_repository import TrackedRepository
from app.models.user import OrgToUser, User
from app.models.user_mcp_token import UserMCPToken
from app.services.embedding_service import embedding_service

Factory = async_sessionmaker[AsyncSession]

# bge-small dimension; any fixed unit vector keeps pgvector maths finite.
_EMBED_DIM = 384


@dataclass(frozen=True)
class Tenant:
    """An org with one member and that member's plaintext MCP token."""

    org_id: uuid.UUID
    user_id: uuid.UUID
    token: str
    token_id: uuid.UUID


async def _fixed_embedding(_text: str) -> list[float]:
    return [1.0] + [0.0] * (_EMBED_DIM - 1)


async def _no_redis() -> None:
    return None


def isolate_side_channels(monkeypatch: pytest.MonkeyPatch, factory: Factory) -> None:
    """Keep audit writes, token touches, redis and embeddings inside the test."""
    monkeypatch.setattr(mcp_audit, "AsyncSessionLocal", factory)
    monkeypatch.setattr(mcp_auth, "AsyncSessionLocal", factory)
    monkeypatch.setattr(mcp_rate_limit, "get_redis", _no_redis)
    monkeypatch.setattr(embedding_service, "embed", _fixed_embedding)


async def drain_background() -> None:
    """Wait for fire-and-forget audit rows and last-used touches to land."""
    pending = [*mcp_audit._audit_tasks, *mcp_auth._last_used_tasks]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def add_member(factory: Factory, org_id: uuid.UUID, name: str = "Dev") -> uuid.UUID:
    """An active member of ``org_id`` with no role (developer permissions)."""
    async with factory() as db:
        user = User(
            email=f"{name.lower()}-{uuid.uuid4().hex[:8]}@acme.dev", name=name, password_hash="x"
        )
        db.add(user)
        await db.flush()
        db.add(OrgToUser(user_id=user.id, org_id=org_id))
        await db.commit()
        return user.id


async def mint_token(
    factory: Factory,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    expires_at: datetime | None = None,
) -> tuple[str, uuid.UUID]:
    """Store a per-user token the way the settings endpoint does."""
    plaintext = secrets.token_urlsafe(32)
    async with factory() as db:
        row = UserMCPToken(
            user_id=user_id,
            org_id=org_id,
            token_hash=hash_password(plaintext),
            token_prefix=compute_token_prefix(plaintext),
            name=f"t-{uuid.uuid4().hex[:8]}",
            expires_at=expires_at,
        )
        db.add(row)
        await db.commit()
        return plaintext, row.id


async def make_tenant(factory: Factory, *, expires_at: datetime | None = None) -> Tenant:
    """A fresh org with one tokened member."""
    async with factory() as db:
        org = Organization(name=f"MCP {uuid.uuid4()}", slug=f"mcp-{uuid.uuid4().hex[:10]}")
        db.add(org)
        await db.commit()
        org_id = org.id
    user_id = await add_member(factory, org_id)
    token, token_id = await mint_token(factory, org_id, user_id, expires_at=expires_at)
    return Tenant(org_id=org_id, user_id=user_id, token=token, token_id=token_id)


async def set_org_token(factory: Factory, org_id: uuid.UUID) -> str:
    """Give the org a legacy org-level token and return its plaintext."""
    plaintext = secrets.token_urlsafe(32)
    async with factory() as db:
        org = await db.get(Organization, org_id)
        assert org is not None
        org.mcp_token_hash = hash_password(plaintext)
        await db.commit()
    return plaintext


async def add_bud(
    factory: Factory,
    org_id: uuid.UUID,
    number: int,
    *,
    title: str = "Task tags",
    status: BUDStatus = BUDStatus.BUD,
    assignee_id: uuid.UUID | None = None,
    requirements_md: str = "Add tags to tasks.",
) -> uuid.UUID:
    """Insert a BUD with an explicit number."""
    async with factory() as db:
        bud = BUDDocument(
            org_id=org_id,
            bud_number=number,
            title=title,
            status=status,
            requirements_md=requirements_md,
            assignee_id=assignee_id,
        )
        db.add(bud)
        await db.commit()
        return bud.id


async def add_todo(
    factory: Factory, org_id: uuid.UUID, bud_id: uuid.UUID, sequence: int, **kw: Any
) -> uuid.UUID:
    """Insert one pending TODO on ``bud_id``."""
    async with factory() as db:
        todo = BUDTodo(
            org_id=org_id,
            bud_id=bud_id,
            sequence=sequence,
            title=kw.pop("title", f"Step {sequence}"),
            context_md=kw.pop("context_md", "secret implementation notes"),
            **kw,
        )
        db.add(todo)
        await db.commit()
        return todo.id


async def add_repo(factory: Factory, org_id: uuid.UUID, name: str) -> uuid.UUID:
    """A tracked repository that has never been scanned."""
    async with factory() as db:
        repo = TrackedRepository(org_id=org_id, path=f"/tmp/{name}-{uuid.uuid4().hex}", name=name)
        db.add(repo)
        await db.commit()
        return repo.id


async def call(
    client: AsyncClient,
    token: str,
    tool: str,
    params: dict[str, Any] | None = None,
    **headers: str,
) -> Response:
    """POST one tool call over the HTTP tool route."""
    return await client.post(
        f"/mcp/tools/{tool}",
        json={"params": params or {}},
        headers={"Authorization": f"Bearer {token}", **headers},
    )


async def audit_rows(factory: Factory, org_id: uuid.UUID) -> list[MCPAuditLogEntry]:
    """Every audit row for ``org_id``, oldest first."""
    await drain_background()
    async with factory() as db:
        rows = await db.scalars(
            select(MCPAuditLogEntry)
            .where(MCPAuditLogEntry.org_id == org_id)
            .order_by(MCPAuditLogEntry.created_at, MCPAuditLogEntry.id)
        )
        return list(rows)
