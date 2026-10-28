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

"""A git author who already has an account in another org must not fail a scan.

User emails are unique across orgs. Skill extraction auto-creates a member
for every unknown git author, and it only checked the scanning org's own
members, so an author with an account elsewhere (a contractor, or a repo two
orgs both track) hit ``uq_users_email`` and failed the repo's whole scan run.
The author is now left unmatched, and the other org's account is not pulled
into this org.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.repositories.user import UserRepository
from app.services.git_analyzer import DevSkillEntry
from app.services.scan.phase_impls.skill_extraction import phase_e_skills

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]


def _entry(email: str, name: str) -> DevSkillEntry:
    return DevSkillEntry(
        email=email,
        author_name=name,
        module="shop/orders",
        languages=["python"],
        touch_count=3,
        lines_added=40,
        lines_removed=2,
        skill_score=0.8,
        last_touch=None,
    )


async def _org(db: AsyncSession) -> uuid.UUID:
    org = Organization(name=f"Org {uuid.uuid4()}", slug=f"org-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()
    return org.id


async def test_author_with_an_account_in_another_org_is_left_unmatched(
    pg_session_factory: Factory,
) -> None:
    shared = f"contractor-{uuid.uuid4().hex[:8]}@acme.dev"
    fresh = f"newcomer-{uuid.uuid4().hex[:8]}@acme.dev"
    async with pg_session_factory() as db:
        other_org, scanning_org = await _org(db), await _org(db)
        owner = User(email=shared, name="Contractor", password_hash="x")
        db.add(owner)
        await db.flush()
        db.add(OrgToUser(user_id=owner.id, org_id=other_org))
        await db.commit()

    async with pg_session_factory() as db:
        email_map: dict[str, User] = {}
        count, unmatched = await phase_e_skills(
            db,
            scanning_org,
            "/tmp/shop",
            [_entry(shared, "Contractor"), _entry(fresh, "Newcomer")],
            email_map,
            {"auto_create_members": True},
        )
        await db.commit()

    assert unmatched == [shared]
    assert count >= 1
    assert set(email_map) == {fresh}
    async with pg_session_factory() as db:
        repo = UserRepository(db)
        assert await repo.get_membership(owner.id, scanning_org) is None
        assert await repo.get_membership(owner.id, other_org) is not None
        newcomer = await repo.get_by_email(fresh)
        assert newcomer is not None
        assert await repo.get_membership(newcomer.id, scanning_org) is not None
