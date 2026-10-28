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

"""Rows the fake-backed tests start from: an org wired to the fakes, members, repos.

Every helper writes through the ORM on the test database and commits, and
every name is unique per call, so tests sharing the session database never
collide.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.encryption import encrypt_secret
from app.core.security import create_access_token
from app.models.organization import Organization
from app.models.tracked_repository import TrackedRepository
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.github import FakeGitHub
from tests.fakes.slack import FakeSlack

Factory = async_sessionmaker[AsyncSession]
WEBHOOK_SECRET = "gh-webhook-secret"
SLACK_SIGNING_SECRET = "slack-signing-secret"
SLACK_BOT_TOKEN = "xoxb-fake-bot-token"


@dataclass(frozen=True)
class SeededOrg:
    """Ids a test needs after seeding."""

    org_id: uuid.UUID
    owner_id: uuid.UUID
    slug: str


async def seed_org(
    factory: Factory,
    *,
    github: FakeGitHub | None = None,
    slack: FakeSlack | None = None,
) -> SeededOrg:
    """An org with an ``org_owner`` member, optionally wired to the fake GitHub / Slack."""
    tag = uuid.uuid4().hex[:8]
    async with factory() as db:
        org = Organization(name=f"Fake Org {tag}", slug=f"fake-{tag}", config={})
        org.github_webhook_secret = encrypt_secret(WEBHOOK_SECRET)
        if github is not None:
            org.github_app_id = github.app_id
            org.github_app_private_key = encrypt_secret(github.private_key_pem)
            org.github_app_installation_id = github.installation_id
            org.github_app_slug = github.app_slug
        if slack is not None:
            org.slack_team_id = slack.team_id
            org.slack_bot_token = encrypt_secret(SLACK_BOT_TOKEN)
            org.slack_signing_secret = encrypt_secret(SLACK_SIGNING_SECRET)
        db.add(org)
        await db.flush()
        owner = await _add_user(db, org.id, f"owner-{tag}", role="org_owner")
        await db.commit()
        return SeededOrg(org_id=org.id, owner_id=owner, slug=org.slug)


async def _add_user(db: AsyncSession, org_id: uuid.UUID, name: str, role: str | None) -> uuid.UUID:
    user = User(email=f"{name}@acme.dev", name=name, password_hash="x")
    db.add(user)
    await db.flush()
    membership = OrgToUser(user_id=user.id, org_id=org_id)
    if role is not None:
        system_role = await RoleRepository(db).get_by_name_system(role)
        assert system_role is not None, f"no system role {role!r}; seed permissions first"
        membership.role_id = system_role.id
    db.add(membership)
    await db.flush()
    return user.id


async def seed_member(
    factory: Factory, org_id: uuid.UUID, name: str, role: str | None = "developer"
) -> uuid.UUID:
    """Add a member with a system ``role`` (``None`` leaves the role unset)."""
    async with factory() as db:
        user_id = await _add_user(db, org_id, f"{name}-{uuid.uuid4().hex[:6]}", role)
        await db.commit()
        return user_id


async def seed_repo(
    factory: Factory,
    org_id: uuid.UUID,
    repo: LocalGitRepo,
    *,
    full_name: str | None = None,
) -> uuid.UUID:
    """Track ``repo`` for ``org_id`` with ``main`` / ``develop`` branches."""
    async with factory() as db:
        row = TrackedRepository(
            org_id=org_id,
            path=repo.path,
            name=repo.name,
            main_branch="main",
            develop_branch="develop",
            github_repo_full_name=full_name or f"acme/{repo.name}",
        )
        db.add(row)
        await db.commit()
        return row.id


def auth_headers(user_id: uuid.UUID, org_id: uuid.UUID) -> dict[str, str]:
    """Bearer headers for ``user_id`` signed in to ``org_id``."""
    token = create_access_token({"sub": str(user_id), "org_id": str(org_id)})
    return {"Authorization": f"Bearer {token}"}
