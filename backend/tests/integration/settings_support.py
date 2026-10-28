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

"""Shared setup for the settings, setup-wizard and integration tests.

Every caller gets a fresh org with fresh users, so tests can share the
session's database without seeing each other's rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.encryption import decrypt_secret
from app.core.security import create_access_token
from app.models.organization import Organization
from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository
from app.services.permission_seeder import seed_permissions

Factory = async_sessionmaker[AsyncSession]


@dataclass(frozen=True)
class Member:
    """One signed-in member of a test org."""

    user_id: uuid.UUID
    org_id: uuid.UUID

    @property
    def headers(self) -> dict[str, str]:
        """Bearer headers for this member in this org."""
        token = create_access_token({"sub": str(self.user_id), "org_id": str(self.org_id)})
        return {"Authorization": f"Bearer {token}"}


@dataclass(frozen=True)
class SeededOrg:
    """An org with an owner and a developer."""

    id: uuid.UUID
    slug: str
    owner: Member
    developer: Member


async def make_org(factory: Factory, prefix: str = "st") -> SeededOrg:
    """A fresh org holding an ``org_owner`` and a ``developer``."""
    slug = f"{prefix}-{uuid.uuid4().hex[:10]}"
    async with factory() as db:
        await seed_permissions(db)
        org = Organization(name=f"Org {slug}", slug=slug, config={})
        db.add(org)
        await db.flush()
        roles = RoleRepository(db)
        members = []
        for role_name in ("org_owner", "developer"):
            role = await roles.get_by_name_system(role_name)
            assert role is not None, role_name
            user = User(
                email=f"{role_name}-{uuid.uuid4().hex[:8]}@{slug}.dev",
                name=role_name,
                password_hash="x",
            )
            db.add(user)
            await db.flush()
            db.add(OrgToUser(user_id=user.id, org_id=org.id, role_id=role.id))
            members.append(Member(user_id=user.id, org_id=org.id))
        await db.commit()
        return SeededOrg(id=org.id, slug=slug, owner=members[0], developer=members[1])


async def add_tracked_repo(factory: Factory, org_id: uuid.UUID, path: str) -> uuid.UUID:
    """A tracked repo row for ``org_id`` at ``path`` on ``main``."""
    async with factory() as db:
        repo = TrackedRepository(
            org_id=org_id,
            path=path,
            name=path.rsplit("/", 1)[-1],
            status=RepoStatus.ACTIVE,
            main_branch="main",
        )
        db.add(repo)
        await db.commit()
        return repo.id


def assert_ciphertext_of(stored: str | None, plaintext: str) -> None:
    """``stored`` is ``plaintext`` encrypted, not ``plaintext`` itself.

    ``decrypt_secret`` hands back a value without the ``enc:`` prefix
    unchanged (legacy rows), so a decrypt round trip alone would also pass
    for a secret stored in the clear.
    """
    assert stored is not None
    assert stored.startswith("enc:"), "stored without the encryption prefix"
    assert plaintext not in stored
    assert decrypt_secret(stored) == plaintext


async def load_org(factory: Factory, org_id: uuid.UUID) -> Organization:
    """A fresh read of the org row."""
    async with factory() as db:
        org = await db.get(Organization, org_id)
        assert org is not None
        return org
