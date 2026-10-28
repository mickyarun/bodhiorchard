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

"""Shared setup for the auth, RBAC and tenant-isolation integration tests.

A :class:`Tenant` is an org with an owner and a developer who can both
sign in with :data:`PASSWORD`. :func:`seed_rows` gives a tenant one row of
each main resource so another org's caller can try to reach them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.bud import BUDDocument, BUDStatus, BUDTimelineEvent
from app.models.bug import Bug
from app.models.bug_comment import BugComment
from app.models.design_system import DesignSystemRef
from app.models.employee_profile import EmployeeProfile
from app.models.feature import Feature
from app.models.leave_request import LeaveKind, LeaveRequest, LeaveStatus
from app.models.leave_type import LeaveType
from app.models.notification import Notification, NotificationType
from app.models.office_location import OfficeLocation
from app.models.organization import Organization
from app.models.quiz_question import QuizQuestion, QuizQuestionType
from app.models.role import Role, RoleScopeType
from app.models.team import Team
from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.models.user import OrgToUser, User
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.role import RoleRepository
from app.services.leave.policies import ensure_default_policy
from tests.integration.leave_support import Factory

PASSWORD = "Orchard-test-pass-1"  # noqa: S105 - a fixture value, not a secret
_HASH = hash_password(PASSWORD)


@dataclass(frozen=True)
class Tenant:
    """An org with an owner and a developer, both able to sign in."""

    org: uuid.UUID
    slug: str
    owner: uuid.UUID
    owner_email: str
    dev: uuid.UUID
    dev_email: str


@dataclass(frozen=True)
class TenantRows:
    """One row of each main resource, all in the same org."""

    bud: uuid.UUID
    bud_number: int
    bug: uuid.UUID
    comment: uuid.UUID
    feature: uuid.UUID
    repo: uuid.UUID
    design_system: uuid.UUID
    team: uuid.UUID
    notification: uuid.UUID
    office: uuid.UUID
    role: uuid.UUID
    leave_request: uuid.UUID
    question: uuid.UUID


async def add_user(
    factory: Factory,
    org: uuid.UUID,
    role_name: str | None,
    *,
    must_change_password: bool = False,
) -> tuple[uuid.UUID, str]:
    """A member of ``org`` holding the system role ``role_name`` (None: no role)."""
    email = f"m-{uuid.uuid4().hex[:10]}@tenancy.dev"
    async with factory() as db:
        role = await RoleRepository(db).get_by_name_system(role_name) if role_name else None
        user = User(
            email=email,
            name=email.split("@")[0],
            password_hash=_HASH,
            must_change_password=must_change_password,
            password_set_at=None if must_change_password else datetime.now(UTC),
        )
        db.add(user)
        await db.flush()
        db.add(OrgToUser(user_id=user.id, org_id=org, role_id=role.id if role else None))
        db.add(EmployeeProfile(org_id=org, user_id=user.id))
        await db.commit()
        return user.id, email


async def new_tenant(factory: Factory) -> Tenant:
    """A fresh org with an ``org_owner`` and a ``developer``."""
    slug = f"tn-{uuid.uuid4().hex[:10]}"
    async with factory() as db:
        org = Organization(name=f"Tenant {slug}", slug=slug)
        db.add(org)
        await db.commit()
        org_id = org.id
    owner, owner_email = await add_user(factory, org_id, "org_owner")
    dev, dev_email = await add_user(factory, org_id, "developer")
    return Tenant(org_id, slug, owner, owner_email, dev, dev_email)


async def seed_rows(factory: Factory, tenant: Tenant) -> TenantRows:
    """One row of each main resource in ``tenant``'s org."""
    org = tenant.org
    async with factory() as db:
        bud = BUDDocument(org_id=org, bud_number=7, title="Tenant BUD", status=BUDStatus.BUD)
        repo = TrackedRepository(org_id=org, name="api", path="/r/api", status=RepoStatus.ACTIVE)
        feature = Feature(
            org_id=org,
            feature_title="Feature: Tenant",
            description="Owned by one org.",
            capabilities={"capabilities": []},
            cluster_names=[],
            tags=[],
            cluster_signature=f"sig-{uuid.uuid4().hex[:8]}",
        )
        team = Team(org_id=org, name="Tenant team")
        office = OfficeLocation(org_id=org, name="Tenant office")
        role = Role(name="Tenant custom", org_id=org, scope_type=RoleScopeType.CUSTOM)
        db.add_all([bud, repo, feature, team, office, role])
        await db.flush()
        bug = Bug(
            org_id=org, bug_number=1, title="Tenant bug", reporter_id=tenant.dev, bud_id=bud.id
        )
        design = DesignSystemRef(
            org_id=org, repo_id=repo.id, content="tokens", extracted_at=datetime.now(UTC)
        )
        notification = Notification(
            org_id=org, user_id=tenant.dev, type=NotificationType.JOB_COMPLETED, title="Done"
        )
        question = QuizQuestion(
            org_id=org,
            question_type=QuizQuestionType.MULTIPLE_CHOICE,
            prompt="Tenant question?",
            payload={"options": ["a", "b"]},
            answer_key={"index": 0},
            topic_hash=uuid.uuid4().hex,
        )
        event = BUDTimelineEvent(org_id=org, bud_id=bud.id, event_type="created")
        db.add_all([bug, design, notification, question, event])
        await db.flush()
        comment = BugComment(bug_id=bug.id, org_id=org, author_id=tenant.dev, body="Tenant note")
        db.add(comment)
        leave_request = await _pending_leave(db, org, tenant.dev)
        await db.commit()
        return TenantRows(
            bud=bud.id,
            bud_number=bud.bud_number,
            bug=bug.id,
            comment=comment.id,
            feature=feature.id,
            repo=repo.id,
            design_system=design.id,
            team=team.id,
            notification=notification.id,
            office=office.id,
            role=role.id,
            leave_request=leave_request,
            question=question.id,
        )


async def _pending_leave(db: AsyncSession, org: uuid.UUID, user: uuid.UUID) -> uuid.UUID:
    """A pending one-day leave request (its dates don't matter to isolation)."""
    policy = await ensure_default_policy(db, org)
    leave_type = await LeaveTypeRepository(db, org_id=org).create(
        LeaveType(
            org_id=org, policy_id=policy.id, name="Casual", code="CL", annual_quota_days=Decimal(5)
        )
    )
    request = LeaveRequest(
        org_id=org,
        user_id=user,
        policy_id=policy.id,
        kind=LeaveKind.LEAVE,
        leave_type_id=leave_type.id,
        start_date=date(2030, 3, 4),
        end_date=date(2030, 3, 4),
        days=Decimal(1),
        status=LeaveStatus.PENDING,
    )
    db.add(request)
    await db.flush()
    return request.id
