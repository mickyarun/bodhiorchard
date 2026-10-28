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
Postgres container is shared across the whole session. ``stub_externals``
replaces every outbound dependency the BUD routes can reach — the ONNX
embedding model, model-backed judges / tie-breaks, the background
estimator (which opens its own session on the app's real database URL)
and the repo-scan entry points — so no test ever leaves the container.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import create_access_token
from app.models.bud import BUDDocument, BUDStatus
from app.models.dev_activity import DevActivityLog
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository
from app.services.embedding_service import embedding_service

Factory = async_sessionmaker[AsyncSession]

# Dimension of ``bud_documents.embedding`` (Vector(384)).
EMBEDDING_DIM = 384

# Every module that imports ``run_agent_for_org_id`` on a path a BUD
# route can reach. Each is patched to raise so the caller's own
# deterministic fallback runs instead of a model call.
_MODEL_CALL_SITES = (
    "app.services.sp_attribution.run_agent_for_org_id",
    "app.services.smart_assignment.run_agent_for_org_id",
    "app.services.estimation_llm.run_agent_for_org_id",
    "app.services._tech_planner_patch_llm.run_agent_for_org_id",
)

# Repo-scan entry points. Closing a BUD must never reach any of them.
_SCAN_ENTRY_POINTS = (
    "app.services.scan.pr_merge_update.start_scan",
    "app.services.scan_kickoff.start_scan",
    "app.services.scan.rescan_enqueue.publish_pr_merge_delivery",
)


@dataclass
class Externals:
    """Handles on the stubs so a test can assert what was (not) reached."""

    embed: AsyncMock
    bg_estimate: AsyncMock
    scans: list[AsyncMock]


@contextmanager
def stub_externals(embedding: list[float] | None = None) -> Iterator[Externals]:
    """Patch every outbound dependency the BUD routes touch."""
    vector = embedding if embedding is not None else [0.01] * EMBEDDING_DIM
    with ExitStack() as stack:
        embed = stack.enter_context(
            patch.object(embedding_service, "embed", new=AsyncMock(return_value=vector))
        )
        for target in _MODEL_CALL_SITES:
            stack.enter_context(
                patch(target, new=AsyncMock(side_effect=RuntimeError("no model in tests")))
            )
        bg_estimate = stack.enter_context(patch("app.api.v1.bud._bg_estimate", new=AsyncMock()))
        scans = [stack.enter_context(patch(t, new=AsyncMock())) for t in _SCAN_ENTRY_POINTS]
        yield Externals(embed=embed, bg_estimate=bg_estimate, scans=scans)


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
    factory: Factory, org_id: uuid.UUID, name: str, role: str | None = "pm"
) -> uuid.UUID:
    """Add a user to ``org_id`` holding the named system role (seeded by ``client``)."""
    async with factory() as db:
        user = User(
            email=f"{name}-{uuid.uuid4().hex[:8]}@example.com",
            name=name,
            password_hash="x",
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
