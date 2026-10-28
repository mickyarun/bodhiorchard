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

"""Shared setup for the scan, features and bugs integration tests.

Every helper creates fresh rows under a new org so tests can share the
session-wide database without seeing each other's data.
"""

from __future__ import annotations

import math
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import create_access_token
from app.models.bud import BUDDocument, BUDStatus
from app.models.feature import Feature
from app.models.feature_to_repo import FeatureToRepo, FeatureToRepoRole
from app.models.organization import Organization
from app.models.tracked_repository import TrackedRepository
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository

Factory = async_sessionmaker[AsyncSession]
DIMS = 384


def vec(*leading: float) -> list[float]:
    """A 384-d vector whose first components are ``leading``, the rest zero.

    Integer components keep pgvector's float4 storage exact, so cosine
    distances against the unit vector ``vec(1)`` are exact fractions.
    """
    return [*leading, *([0.0] * (DIMS - len(leading)))]


def cosine_distance(a: list[float], b: list[float]) -> float:
    """Reference cosine distance, computed the way pgvector does (float8)."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return 1.0 - dot / norm


def as_user(user: uuid.UUID, org: uuid.UUID) -> dict[str, str]:
    """Bearer headers for ``user`` signed in to ``org``."""
    token = create_access_token({"sub": str(user), "org_id": str(org)})
    return {"Authorization": f"Bearer {token}"}


async def new_org(factory: Factory, **cols: Any) -> uuid.UUID:
    """A fresh organisation; ``cols`` set extra columns."""
    async with factory() as db:
        org = Organization(name=f"Org {uuid.uuid4()}", slug=f"o-{uuid.uuid4().hex[:10]}", **cols)
        db.add(org)
        await db.commit()
        return org.id


async def new_member(factory: Factory, org: uuid.UUID, role: str | None = None) -> uuid.UUID:
    """A member of ``org`` holding the system role ``role`` (none when omitted)."""
    async with factory() as db:
        user = User(email=f"u-{uuid.uuid4().hex[:10]}@acme.dev", name="Tess", password_hash="x")
        db.add(user)
        await db.flush()
        role_id = None
        if role is not None:
            found = await RoleRepository(db).get_by_name_system(role)
            assert found is not None, role
            role_id = found.id
        db.add(OrgToUser(user_id=user.id, org_id=org, role_id=role_id))
        await db.commit()
        return user.id


async def new_repo(factory: Factory, org: uuid.UUID, **cols: Any) -> uuid.UUID:
    """A tracked repository in ``org``; ``cols`` override the defaults."""
    defaults: dict[str, Any] = {
        "path": f"/tmp/{uuid.uuid4().hex}",
        "name": f"repo-{uuid.uuid4().hex[:6]}",
    }
    async with factory() as db:
        repo = TrackedRepository(org_id=org, **{**defaults, **cols})
        db.add(repo)
        await db.commit()
        return repo.id


async def new_bud(
    factory: Factory,
    org: uuid.UUID,
    number: int,
    *,
    status: BUDStatus = BUDStatus.TESTING,
    embedding: list[float] | None = None,
    **cols: Any,
) -> uuid.UUID:
    """A BUD numbered ``number`` in ``org``."""
    async with factory() as db:
        bud = BUDDocument(
            org_id=org,
            bud_number=number,
            title=f"BUD {number}",
            status=status,
            embedding=embedding,
            **cols,
        )
        db.add(bud)
        await db.commit()
        return bud.id


async def new_feature(
    factory: Factory,
    org: uuid.UUID,
    title: str,
    *,
    embedding: list[float] | None = None,
    repo: uuid.UUID | None = None,
    active: bool = True,
    **cols: Any,
) -> uuid.UUID:
    """A scan-style feature, with a PRIMARY junction to ``repo`` when given."""
    async with factory() as db:
        feature = Feature(
            org_id=org,
            feature_title=title,
            description=f"{title} description",
            capabilities={"capabilities": []},
            cluster_names=[],
            tags=[],
            cluster_signature=uuid.uuid4().hex,
            embedding=embedding,
            is_active=active,
            **cols,
        )
        db.add(feature)
        await db.flush()
        if repo is not None:
            db.add(
                FeatureToRepo(
                    feature_id=feature.id,
                    repo_id=repo,
                    role=FeatureToRepoRole.PRIMARY,
                    feature_title=title,
                )
            )
        await db.commit()
        return feature.id
