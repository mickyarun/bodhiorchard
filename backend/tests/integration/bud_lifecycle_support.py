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

"""Shared helpers for the BUD lifecycle integration tests.

Every helper writes on fresh uuids (a new org per test) because the
Postgres container is shared across the whole session.

Two layers keep the tests inside the container:

* ``stub_externals`` replaces the outbound dependencies the BUD routes
  reach on purpose: the ONNX embedding model, every model call (at the
  provider choke point and at the importer sites that would otherwise
  open their own session first), and the background estimators, which
  open sessions on the app's own database URL.
* ``app_database_blocked`` is the fail-closed backstop. Test modules
  import it (``import ... as ...``), so it runs autouse: any attempt to
  connect through ``app.database.engine`` (the real ``DATABASE_URL``) is
  refused and recorded, and the test fails at teardown even when the
  code under test swallowed the error.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import create_access_token
from app.database import engine as app_engine
from app.models.bud import BUDDocument, BUDStatus
from app.models.dev_activity import DevActivityLog
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository
from app.services.embedding_service import embedding_service

Factory = async_sessionmaker[AsyncSession]

# Dimension of ``bud_documents.embedding`` (Vector(384)).
EMBEDDING_DIM = 384

_NO_MODEL = "no model in tests"

# Importers of ``run_agent_for_org_id`` on paths a BUD route can reach.
# Patched to raise before the function opens its own app-database
# session to look the org up; the caller's deterministic fallback runs.
_MODEL_CALL_SITES = (
    "app.services.sp_attribution.run_agent_for_org_id",
    "app.services.smart_assignment.run_agent_for_org_id",
    "app.services.estimation_llm.run_agent_for_org_id",
    "app.services._tech_planner_patch_llm.run_agent_for_org_id",
)


@pytest.fixture(autouse=True)
def app_database_blocked() -> Iterator[list[str]]:
    """Refuse and record every connection attempt on the app's own engine."""
    attempts: list[str] = []

    def _refuse(*_args: object) -> None:
        attempts.append("connect")
        raise RuntimeError("test tried to connect to the app database")

    sync_engine = app_engine.sync_engine
    event.listen(sync_engine, "do_connect", _refuse)
    try:
        yield attempts
    finally:
        event.remove(sync_engine, "do_connect", _refuse)
    assert attempts == [], "code under test opened a session on the app database"


@dataclass
class Externals:
    """Handles on the stubs so a test can assert what was (not) reached."""

    embed: AsyncMock
    bg_estimate: AsyncMock
    dev_estimate: MagicMock


@contextmanager
def stub_externals(embedding: list[float] | None = None) -> Iterator[Externals]:
    """Patch every outbound dependency the BUD routes touch."""
    vector = embedding if embedding is not None else [0.01] * EMBEDDING_DIM
    with ExitStack() as stack:
        embed = stack.enter_context(
            patch.object(embedding_service, "embed", new=AsyncMock(return_value=vector))
        )
        stack.enter_context(
            patch(
                "app.services.ai_runner.provider_for",
                new=MagicMock(side_effect=RuntimeError(_NO_MODEL)),
            )
        )
        for target in _MODEL_CALL_SITES:
            stack.enter_context(patch(target, new=AsyncMock(side_effect=RuntimeError(_NO_MODEL))))
        bg_estimate = stack.enter_context(patch("app.api.v1.bud._bg_estimate", new=AsyncMock()))
        dev_estimate = stack.enter_context(
            patch("app.services.bud_development._schedule_estimation_after_commit")
        )
        yield Externals(embed=embed, bg_estimate=bg_estimate, dev_estimate=dev_estimate)


def as_user(user_id: uuid.UUID, org_id: uuid.UUID) -> dict[str, str]:
    """Bearer auth headers for ``user_id`` signed in to ``org_id``."""
    token = create_access_token({"sub": str(user_id), "org_id": str(org_id)})
    return {"Authorization": f"Bearer {token}"}


async def new_org(factory: Factory, config: dict[str, Any] | None = None) -> uuid.UUID:
    """Create an empty organisation and return its id."""
    async with factory() as db:
        org = Organization(
            name=f"BUD {uuid.uuid4()}",
            slug=f"bud-{uuid.uuid4().hex[:10]}",
            config=config or {},
        )
        db.add(org)
        await db.commit()
        return org.id


async def add_member(
    factory: Factory,
    org_id: uuid.UUID,
    name: str,
    role: str | None = "pm",
    *,
    github: str | None = None,
) -> uuid.UUID:
    """Add a user to ``org_id`` holding the named system role."""
    async with factory() as db:
        user = User(
            email=f"{name}-{uuid.uuid4().hex[:8]}@example.com",
            name=name,
            password_hash="x",
            github_username=github,
        )
        db.add(user)
        await db.flush()
        role_id = None
        if role is not None:
            role_row = await RoleRepository(db).get_by_name_system(role)
            assert role_row is not None, f"system role {role!r} not seeded"
            role_id = role_row.id
        db.add(OrgToUser(user_id=user.id, org_id=org_id, role_id=role_id))
        await db.commit()
        return user.id


async def add_bud(
    factory: Factory,
    org_id: uuid.UUID,
    *,
    number: int = 1,
    status: BUDStatus = BUDStatus.BUD,
    **fields: Any,
) -> uuid.UUID:
    """Insert a BUD row directly in ``status`` and return its id."""
    async with factory() as db:
        bud = BUDDocument(
            org_id=org_id,
            bud_number=number,
            title=fields.pop("title", f"BUD {number}"),
            status=status,
            **fields,
        )
        db.add(bud)
        await db.commit()
        return bud.id


async def add_commit(
    factory: Factory, org_id: uuid.UUID, bud_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Record one commit by ``user_id`` on the BUD (a closure contributor)."""
    async with factory() as db:
        db.add(
            DevActivityLog(
                org_id=org_id,
                bud_id=bud_id,
                user_id=user_id,
                event_type="commit",
                source="hook",
                commit_sha=uuid.uuid4().hex[:40],
            )
        )
        await db.commit()


def manual_cases(*results: str) -> list[dict[str, Any]]:
    """Manual cases MTC-001.. with the given results, as the QA agent stores them."""
    return [
        {"id": f"MTC-{i:03d}", "title": f"case {i}", "result": r, "tester_name": None}
        for i, r in enumerate(results, start=1)
    ]


async def bud_in_testing(factory: Factory, *results: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Org + a testing-phase BUD holding manual cases with ``results``."""
    org = await new_org(factory)
    bud_id = await add_bud(
        factory, org, status=BUDStatus.TESTING, qa_manual_cases=manual_cases(*results)
    )
    return org, bud_id
