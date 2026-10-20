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

"""Shared setup for the leave integration tests.

Dates come from :func:`future_monday` / :func:`month_mondays`, which never
let a test's week cross into the next leave year, so the suite doesn't
start failing in December.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.deps import PermissionSet
from app.core.security import create_access_token
from app.models.employee_profile import EmployeeProfile
from app.models.leave_request import LeaveKind, LeaveRequest, LeaveStatus
from app.models.leave_type import LeaveType
from app.models.organization import Organization
from app.models.permission import Permission
from app.models.role import Role, RolePermission, RoleScopeType
from app.models.user import OrgToUser, User
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.employee_reporting_manager import EmployeeReportingManagerRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.role import RoleRepository
from app.repositories.user import UserRepository
from app.schemas.leave import LeaveRequestCreate
from app.services.leave.policies import ensure_default_policy

Factory = async_sessionmaker[AsyncSession]
NOBODY = PermissionSet(ids=frozenset(), is_owner=False)
HR = PermissionSet(ids=frozenset({"leave:approve"}), is_owner=False)


def future_monday(weeks: int = 2) -> date:
    """A Monday a few weeks out; that week and the next stay in one year.

    Near year end it jumps to the second Monday of January instead.
    """
    today = date.today()
    monday = today + timedelta(days=(7 - today.weekday()) % 7 + 7 * weeks)
    if (monday + timedelta(days=13)).year != monday.year:
        eighth = date(monday.year + 1, 1, 8)
        monday = eighth + timedelta(days=(7 - eighth.weekday()) % 7)
    return monday


def month_mondays(months_ahead: int = 2) -> list[date]:
    """The first three Mondays of a month ``months_ahead`` from now."""
    first = (date.today().replace(day=1) + timedelta(days=32 * months_ahead)).replace(day=1)
    day = first + timedelta(days=(7 - first.weekday()) % 7)
    return [day + timedelta(weeks=n) for n in range(3)]


async def setup_org(factory: Factory, *names: str) -> tuple[uuid.UUID, list[uuid.UUID], uuid.UUID]:
    """Org with members (each with a profile), a default policy and a 5-day type."""
    async with factory() as db:
        org = Organization(name=f"Leave {uuid.uuid4()}", slug=f"leave-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        ids = []
        for name in names:
            user = User(
                email=f"{name}-{uuid.uuid4().hex[:6]}@acme.dev", name=name, password_hash="x"
            )
            db.add(user)
            await db.flush()
            db.add(OrgToUser(user_id=user.id, org_id=org.id))
            db.add(EmployeeProfile(org_id=org.id, user_id=user.id))
            ids.append(user.id)
        policy = await ensure_default_policy(db, org.id)
        leave_type = await LeaveTypeRepository(db, org_id=org.id).create(
            LeaveType(
                org_id=org.id,
                policy_id=policy.id,
                name="Casual",
                code="CL",
                annual_quota_days=Decimal("5"),
            )
        )
        await db.commit()
        return org.id, ids, leave_type.id


async def report_to(
    factory: Factory, org: uuid.UUID, employee: uuid.UUID, *managers: uuid.UUID
) -> None:
    async with factory() as db:
        profile = await EmployeeProfileRepository(db, org_id=org).get_by_user(employee)
        assert profile is not None
        await EmployeeReportingManagerRepository(db, org_id=org).replace_for_profile(
            profile.id, [(m, i == 0) for i, m in enumerate(managers)]
        )
        await db.commit()


async def give_role(factory: Factory, org: uuid.UUID, user: uuid.UUID, role_name: str) -> None:
    """Give ``user`` a system role (``hr``, ``admin``, …) in ``org``."""
    async with factory() as db:
        role = await RoleRepository(db).get_by_name_system(role_name)
        assert role is not None
        membership = await UserRepository(db).get_membership(user, org)
        assert membership is not None
        membership.role_id = role.id
        await db.commit()


async def give_custom_role(
    factory: Factory, org: uuid.UUID, user: uuid.UUID, *permissions: str
) -> None:
    """Give ``user`` a custom role in ``org`` holding exactly ``permissions``."""
    async with factory() as db:
        role = Role(
            name=f"custom-{uuid.uuid4().hex[:8]}", org_id=org, scope_type=RoleScopeType.CUSTOM
        )
        db.add(role)
        await db.flush()
        rows = await db.scalars(select(Permission).where(Permission.resource_id.in_(permissions)))
        db.add_all(RolePermission(role_id=role.id, permission_id=p.id) for p in rows)
        membership = await UserRepository(db).get_membership(user, org)
        assert membership is not None
        membership.role_id = role.id
        await db.commit()


def leave_body(type_id: uuid.UUID, start: date, end: date, **kw: object) -> LeaveRequestCreate:
    """A leave request of type ``type_id``."""
    return LeaveRequestCreate(
        kind=LeaveKind.LEAVE, leave_type_id=type_id, start_date=start, end_date=end, **kw
    )  # type: ignore[arg-type]


def as_user(user: uuid.UUID, org: uuid.UUID) -> dict[str, str]:
    """Auth headers for ``user`` signed in to ``org``."""
    token = create_access_token({"sub": str(user), "org_id": str(org)})
    return {"Authorization": f"Bearer {token}"}


async def add_request(
    factory: Factory,
    org: uuid.UUID,
    user: uuid.UUID,
    start: date,
    end: date,
    days: str,
    *,
    type_id: uuid.UUID | None = None,
    lop: str = "0",
    kind: LeaveKind = LeaveKind.LEAVE,
    status: LeaveStatus = LeaveStatus.APPROVED,
    decided_by: uuid.UUID | None = None,
    decided_at: datetime | None = None,
) -> None:
    """Insert a request as booked, skipping the submit rules (dates may be past)."""
    async with factory() as db:
        policy = await ensure_default_policy(db, org)
        db.add(
            LeaveRequest(
                org_id=org, user_id=user, policy_id=policy.id, kind=kind,
                leave_type_id=type_id if kind == LeaveKind.LEAVE else None,
                start_date=start, end_date=end, days=Decimal(days), lop_days=Decimal(lop),
                status=status, decided_by=decided_by, decided_at=decided_at,
            )
        )  # fmt: skip
        await db.commit()
