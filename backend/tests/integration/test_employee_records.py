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

"""Employee records against real Postgres: indexes, managers, merge."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.employee_profile import EmployeeProfile
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.employee_reporting_manager import EmployeeReportingManagerRepository
from app.services.employees.merge import (
    EmployeeMergeConflictError,
    transfer_employee_record,
)

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]


async def _org(factory: Factory) -> uuid.UUID:
    async with factory() as db:
        org = Organization(name=f"People {uuid.uuid4()}", slug=f"people-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.commit()
        return org.id


async def _member(
    factory: Factory, org_id: uuid.UUID, name: str, *, active: bool = True
) -> uuid.UUID:
    async with factory() as db:
        user = User(
            email=f"{name}-{uuid.uuid4().hex[:6]}@acme.dev",
            name=name,
            password_hash="x",
            is_active=active,
        )
        db.add(user)
        await db.flush()
        db.add(OrgToUser(user_id=user.id, org_id=org_id))
        await db.commit()
        return user.id


async def _members(factory: Factory, org_id: uuid.UUID, *names: str) -> list[uuid.UUID]:
    return [await _member(factory, org_id, name) for name in names]


async def _profile(
    factory: Factory, org_id: uuid.UUID, user_id: uuid.UUID, code: str | None = None
) -> uuid.UUID:
    async with factory() as db:
        profile = await EmployeeProfileRepository(db, org_id=org_id).create(
            EmployeeProfile(org_id=org_id, user_id=user_id, employee_code=code)
        )
        await db.commit()
        return profile.id


async def test_directory_lists_only_members_with_records(pg_session_factory: Factory) -> None:
    org = await _org(pg_session_factory)
    ana = await _member(pg_session_factory, org, "Ana")
    ben = await _member(pg_session_factory, org, "Ben")
    await _profile(pg_session_factory, org, ana)
    async with pg_session_factory() as db:
        repo = EmployeeProfileRepository(db, org_id=org)
        assert [r.name for r in await repo.list_directory()] == ["Ana"]
        assert [m.user_id for m in await repo.list_members_without_profile()] == [ben]


async def test_employee_code_unique_per_org(pg_session_factory: Factory) -> None:
    org = await _org(pg_session_factory)
    await _profile(pg_session_factory, org, await _member(pg_session_factory, org, "Ana"), "E-1")
    with pytest.raises(IntegrityError):
        await _profile(
            pg_session_factory, org, await _member(pg_session_factory, org, "Ben"), "E-1"
        )
    # Another org may reuse the code.
    other = await _org(pg_session_factory)
    await _profile(
        pg_session_factory, other, await _member(pg_session_factory, other, "Cy"), "E-1"
    )


async def test_replace_managers_keeps_one_primary(pg_session_factory: Factory) -> None:
    org = await _org(pg_session_factory)
    emp, m1, m2 = await _members(pg_session_factory, org, "Emp", "M1", "M2")
    profile = await _profile(pg_session_factory, org, emp)
    async with pg_session_factory() as db:
        links = EmployeeReportingManagerRepository(db, org_id=org)
        await links.replace_for_profile(profile, [(m1, True), (m2, False)])
        # Swapping the primary in one replace must not trip the partial index.
        await links.replace_for_profile(profile, [(m1, False), (m2, True)])
        await db.commit()
        result = (await links.list_for_profiles([profile]))[profile]
        assert [(link.name, link.is_primary) for link in result] == [("M2", True), ("M1", False)]
        assert set(await links.reporting_edges()) == {(emp, m1), (emp, m2)}


async def test_active_member_ids_excludes_inactive_and_other_orgs(
    pg_session_factory: Factory,
) -> None:
    org, other = await _org(pg_session_factory), await _org(pg_session_factory)
    active = await _member(pg_session_factory, org, "Active")
    gone = await _member(pg_session_factory, org, "Gone", active=False)
    stranger = await _member(pg_session_factory, other, "Stranger")
    async with pg_session_factory() as db:
        links = EmployeeReportingManagerRepository(db, org_id=org)
        assert await links.active_member_ids([active, gone, stranger]) == {active}


async def test_merge_moves_record_and_reports(pg_session_factory: Factory) -> None:
    org = await _org(pg_session_factory)
    stub, real, report = await _members(pg_session_factory, org, "Stub", "Real", "Report")
    await _profile(pg_session_factory, org, stub)
    report_profile = await _profile(pg_session_factory, org, report)
    async with pg_session_factory() as db:
        await EmployeeReportingManagerRepository(db, org_id=org).replace_for_profile(
            report_profile, [(stub, True)]
        )
        result = await transfer_employee_record(db, org_id=org, source=stub, target=real)
        await db.commit()
        assert result.profile_moved and result.reports_moved == 1
        profiles = EmployeeProfileRepository(db, org_id=org)
        assert await profiles.get_by_user(real) is not None
        assert await profiles.get_by_user(stub) is None
        links = await EmployeeReportingManagerRepository(db, org_id=org).list_for_profiles(
            [report_profile]
        )
        assert [link.user_id for link in links[report_profile]] == [real]


async def test_merge_drops_link_that_would_self_manage(pg_session_factory: Factory) -> None:
    org = await _org(pg_session_factory)
    stub, real = await _members(pg_session_factory, org, "Stub", "Real")
    real_profile = await _profile(pg_session_factory, org, real)
    async with pg_session_factory() as db:
        await EmployeeReportingManagerRepository(db, org_id=org).replace_for_profile(
            real_profile, [(stub, True)]
        )
        await transfer_employee_record(db, org_id=org, source=stub, target=real)
        await db.commit()
        links = await EmployeeReportingManagerRepository(db, org_id=org).list_for_profiles(
            [real_profile]
        )
        assert links == {}


async def test_merge_refuses_when_both_have_records(pg_session_factory: Factory) -> None:
    org = await _org(pg_session_factory)
    a, b = await _members(pg_session_factory, org, "A", "B")
    await _profile(pg_session_factory, org, a)
    await _profile(pg_session_factory, org, b)
    async with pg_session_factory() as db:
        with pytest.raises(EmployeeMergeConflictError):
            await transfer_employee_record(db, org_id=org, source=a, target=b)


async def test_merge_keeps_one_primary_when_primary_link_is_dropped(
    pg_session_factory: Factory,
) -> None:
    # Report lists Stub (primary) and Real; merging Stub into Real drops the
    # primary duplicate, so Real's link must become primary.
    org = await _org(pg_session_factory)
    stub, real, report = await _members(pg_session_factory, org, "Stub", "Real", "Report")
    report_profile = await _profile(pg_session_factory, org, report)
    async with pg_session_factory() as db:
        await EmployeeReportingManagerRepository(db, org_id=org).replace_for_profile(
            report_profile, [(stub, True), (real, False)]
        )
        await transfer_employee_record(db, org_id=org, source=stub, target=real)
        await db.commit()
        links = await EmployeeReportingManagerRepository(db, org_id=org).list_for_profiles(
            [report_profile]
        )
        assert [(link.user_id, link.is_primary) for link in links[report_profile]] == [
            (real, True)
        ]


async def test_merge_refuses_to_create_a_reporting_loop(pg_session_factory: Factory) -> None:
    # Real reports to X; Stub manages X. Merging Stub into Real would make
    # Real manage X while reporting to X.
    org = await _org(pg_session_factory)
    stub, real, x = await _members(pg_session_factory, org, "Stub", "Real", "X")
    real_profile = await _profile(pg_session_factory, org, real)
    x_profile = await _profile(pg_session_factory, org, x)
    async with pg_session_factory() as db:
        links = EmployeeReportingManagerRepository(db, org_id=org)
        await links.replace_for_profile(real_profile, [(x, True)])
        await links.replace_for_profile(x_profile, [(stub, True)])
        await db.commit()
        with pytest.raises(EmployeeMergeConflictError, match="loop"):
            await transfer_employee_record(db, org_id=org, source=stub, target=real)


async def test_directory_search_treats_wildcards_literally(pg_session_factory: Factory) -> None:
    org = await _org(pg_session_factory)
    ana, ben = await _members(pg_session_factory, org, "Ana", "Ben")
    await _profile(pg_session_factory, org, ana, "E_1")
    await _profile(pg_session_factory, org, ben, "EX1")
    async with pg_session_factory() as db:
        rows = await EmployeeProfileRepository(db, org_id=org).list_directory(search="E_1")
        assert [row.name for row in rows] == ["Ana"]
