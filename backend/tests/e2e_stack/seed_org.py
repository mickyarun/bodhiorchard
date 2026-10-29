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

"""Create the org, members and leave setup one browser test starts from.

Mirrors what ``init-org`` provisions (permissions, skills, stage mappings) so
a seeded org behaves like one made by the setup wizard, then adds members
with employee profiles, reporting lines and leave types. Every name and
email carries a random tag, so tests running in parallel never collide.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.employee_profile import EmployeeProfile
from app.models.leave_type import LeaveType
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.repositories.employee_reporting_manager import EmployeeReportingManagerRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.role import RoleRepository
from app.services.bud_stage_seeder import seed_stage_mappings_for_org
from app.services.leave.policies import ensure_default_policy
from app.services.permission_seeder import seed_permissions
from app.services.skill_loader import seed_skills_for_org
from tests.e2e_stack.seed_content import add_features, add_open_quiz
from tests.e2e_stack.specs import MemberSpec, OrgSpec, SeededMember, SeededOrg

EMAIL_DOMAIN = "e2e.example.com"
# Any constant works: it only has to be the same for every primary-org seed.
_PRIMARY_ORG_LOCK = 0x6532_6501


async def _org_for(db: AsyncSession, spec: OrgSpec, tag: str) -> Organization:
    if spec.primary:
        # Parallel tests seed the primary org at once; on an empty database
        # each would otherwise create its own. Held until the seed commits.
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _PRIMARY_ORG_LOCK})
        oldest = await OrganizationRepository(db).check_setup_exists()
        if oldest is not None:
            return oldest
    config = {} if spec.quiz else {"quiz": {"enabled": False}}
    org = Organization(name=f"E2E Org {tag}", slug=f"e2e-{tag}", config=config)
    db.add(org)
    await db.flush()
    await seed_skills_for_org(org.id, db)
    await seed_stage_mappings_for_org(org.id, db)
    return org


async def _add_member(
    db: AsyncSession, org_id: uuid.UUID, member: MemberSpec, password_hash: str, tag: str
) -> tuple[User, EmployeeProfile]:
    role_id = None
    if member.role is not None:
        role = await RoleRepository(db).get_by_name_system(member.role)
        if role is None:
            raise HTTPException(status_code=400, detail=f"no system role {member.role!r}")
        role_id = role.id
    name = member.name or f"{member.key.replace('_', ' ').title()} {tag}"
    user = User(
        email=f"{member.key}-{tag}@{EMAIL_DOMAIN}",
        name=name,
        password_hash=password_hash,
        must_change_password=member.must_change_password,
        password_set_at=None if member.must_change_password else datetime.now(UTC),
        character_model=member.character_model,
    )
    db.add(user)
    await db.flush()
    db.add(OrgToUser(user_id=user.id, org_id=org_id, role_id=role_id))
    profile = EmployeeProfile(org_id=org_id, user_id=user.id)
    db.add(profile)
    await db.flush()
    return user, profile


async def _add_leave_types(
    db: AsyncSession, org_id: uuid.UUID, spec: OrgSpec
) -> dict[str, uuid.UUID]:
    policy = await ensure_default_policy(db, org_id)
    repo = LeaveTypeRepository(db, org_id=org_id)
    ids: dict[str, uuid.UUID] = {}
    for leave_type in spec.leave_types:
        row = await repo.create(
            LeaveType(
                org_id=org_id,
                policy_id=policy.id,
                name=leave_type.name,
                code=leave_type.code,
                annual_quota_days=leave_type.quota_days,
            )
        )
        ids[leave_type.code] = row.id
    return ids


async def seed_org(db: AsyncSession, spec: OrgSpec) -> SeededOrg:
    """Create everything in ``spec`` and commit."""
    keys = [m.key for m in spec.members]
    if len(set(keys)) != len(keys):
        raise HTTPException(status_code=400, detail="member keys must be unique")
    unknown = {m.manager for m in spec.members if m.manager} - set(keys)
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown managers: {sorted(unknown)}")

    tag = uuid.uuid4().hex[:8]
    await seed_permissions(db)
    org = await _org_for(db, spec, tag)
    password_hash = hash_password(spec.password)
    users: dict[str, tuple[User, EmployeeProfile]] = {}
    for member in spec.members:
        users[member.key] = await _add_member(db, org.id, member, password_hash, tag)

    lines = EmployeeReportingManagerRepository(db, org_id=org.id)
    for member in spec.members:
        if member.manager:
            _, profile = users[member.key]
            manager, _ = users[member.manager]
            await lines.replace_for_profile(profile.id, [(manager.id, True)])

    # The primary org is shared by every login test; leave tests get their own.
    leave_types = {} if spec.primary else await _add_leave_types(db, org.id, spec)
    add_features(db, org.id, spec)
    await add_open_quiz(db, org.id, spec)
    await db.commit()
    return SeededOrg(
        id=org.id,
        slug=org.slug,
        name=org.name,
        members={
            key: SeededMember(id=user.id, email=user.email, name=user.name)
            for key, (user, _) in users.items()
        },
        leave_types=leave_types,
    )
