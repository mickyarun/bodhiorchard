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

"""Helpers for scans that check which member each git author becomes."""

from __future__ import annotations

import dataclasses
import uuid

from httpx import AsyncClient

from app.models.scan_phase import ScanPhase
from app.models.user import User
from app.repositories.skill_profile import SkillProfileRepository
from app.repositories.user import UserRepository
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.seed import SeededOrg, auth_headers, seed_repo
from tests.integration.scan_e2e.scan_support import Factory, load_outcome, start_scan_over_http

# Skill extraction walks the develop branch when the repo has one.
SKILL_BRANCH = "develop"


@dataclasses.dataclass(frozen=True)
class ScanResult:
    """The tracked repo and the scan that just ran over it."""

    repo_id: uuid.UUID
    scan_id: uuid.UUID


def personal_address() -> str:
    """A fresh real-looking address no member owns yet."""
    return f"dev-{uuid.uuid4().hex[:8]}@mail.example.test"


def commit_as(repo: LocalGitRepo, email: str, files: dict[str, str]) -> str:
    """Commit ``files`` on the skill branch under another author's address."""
    other = dataclasses.replace(repo, author_email=email)
    return other.commit(files, f"Work by {email}", branch=SKILL_BRANCH)


async def scan(
    client: AsyncClient,
    factory: Factory,
    org: SeededOrg,
    repo: LocalGitRepo,
    *,
    repo_id: uuid.UUID | None = None,
) -> ScanResult:
    """Track ``repo`` (first time only) and run a full scan over it."""
    tracked = repo_id or await seed_repo(factory, org.org_id, repo)
    headers = auth_headers(org.owner_id, org.org_id)
    scan_id = await start_scan_over_http(client, headers, tracked, full_rescan=True)
    return ScanResult(repo_id=tracked, scan_id=scan_id)


async def add_alias(factory: Factory, org_id: uuid.UUID, user_id: uuid.UUID, email: str) -> None:
    """Record ``email`` as an alias of ``user_id``."""
    async with factory() as db:
        await UserRepository(db).add_email_alias(org_id, user_id, email)
        await db.commit()


async def org_member_emails(factory: Factory, org_id: uuid.UUID) -> set[str]:
    """Primary emails of every member of the org, active or not."""
    async with factory() as db:
        return {user.email for user in await UserRepository(db).list_by_org(org_id)}


async def member_by_email(factory: Factory, org_id: uuid.UUID, email: str) -> User | None:
    """The org member whose primary email is ``email`` (case-insensitive)."""
    async with factory() as db:
        for user in await UserRepository(db).list_by_org(org_id):
            if user.email.lower() == email.lower():
                return user
        return None


async def holds_profiles(factory: Factory, org_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Whether the scan left any skill profile on ``user_id``."""
    async with factory() as db:
        return bool(await SkillProfileRepository(db, org_id=org_id).list_for_user(user_id))


async def unmatched_authors(factory: Factory, org_id: uuid.UUID, scan_id: uuid.UUID) -> list[str]:
    """The unmatched author emails the skill-extraction step reported."""
    outcome = await load_outcome(factory, org_id, scan_id)
    (step,) = [s for s in outcome.steps if s.phase is ScanPhase.SKILL_EXTRACTION]
    return list(step.extras.get("unmatched_emails", []))


async def aliases_of(factory: Factory, user_id: uuid.UUID) -> set[str]:
    """Alias addresses recorded on ``user_id``."""
    async with factory() as db:
        return {alias.email for alias in await UserRepository(db).list_aliases(user_id)}


async def set_github_login(factory: Factory, user_id: uuid.UUID, login: str) -> None:
    """Give a member a GitHub login."""
    async with factory() as db:
        user = await UserRepository(db).get_by_id(user_id)
        assert user is not None
        user.github_username = login
        await db.commit()
