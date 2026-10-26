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

"""Celebrations against real Postgres: who gets announced, and who decides.

Unit tests fake the repositories; these run the actual SQL — the month/day
match, every exclusion, leap days, anniversary counts — plus the opt-out
endpoint, the shared-member photo rule and the settings audit trail through
the real HTTP stack.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.models.celebration_config_event import CelebrationConfigEvent
from app.models.employee_profile import EmployeeProfile, EmployeeStatus
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.repositories.employee_profile import EmployeeProfileRepository
from app.services.avatars import shared_member_ids
from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration

OCT_22 = date(2026, 10, 22)


async def _set_profile(factory: Factory, user_id: uuid.UUID, **values: object) -> None:
    async with factory() as db:
        await db.execute(
            update(EmployeeProfile).where(EmployeeProfile.user_id == user_id).values(**values)
        )
        await db.commit()


async def test_who_is_announced(pg_session_factory: Factory) -> None:
    org, people, _ = await setup_org(
        pg_session_factory,
        "Birthday",  # birthday today
        "Muted",  # birthday today, opted out
        "Exited",  # birthday today, left the company
        "Notice",  # birthday today, serving notice — still celebrated
        "Inactive",  # birthday today, login deactivated
        "Prejoin",  # birthday today, hasn't started yet
        "Twoyears",  # joined two years ago today
        "Joiner",  # joins today — day zero, not an anniversary
        "Other",  # birthday tomorrow
    )
    birthday, muted, exited, notice, inactive, prejoin, twoyears, joiner, other = people
    dob = date(1990, 10, 22)
    for user in (birthday, muted, exited, notice, inactive, prejoin):
        await _set_profile(pg_session_factory, user, date_of_birth=dob)
    await _set_profile(pg_session_factory, muted, celebrate_birthday=False)
    await _set_profile(pg_session_factory, exited, status=EmployeeStatus.EXITED)
    await _set_profile(pg_session_factory, notice, status=EmployeeStatus.ON_NOTICE)
    await _set_profile(pg_session_factory, prejoin, date_of_joining=date(2026, 11, 3))
    await _set_profile(pg_session_factory, twoyears, date_of_joining=date(2024, 10, 22))
    await _set_profile(pg_session_factory, joiner, date_of_joining=OCT_22)
    await _set_profile(pg_session_factory, other, date_of_birth=date(1991, 10, 23))
    async with pg_session_factory() as db:
        await db.execute(update(User).where(User.id == inactive).values(is_active=False))
        await db.commit()

    # Someone in another org with the same birthday must never leak in.
    _other_org, (stranger,), _ = await setup_org(pg_session_factory, "Stranger")
    await _set_profile(pg_session_factory, stranger, date_of_birth=dob)

    async with pg_session_factory() as db:
        repo = EmployeeProfileRepository(db, org_id=org)
        birthdays, anniversaries = await repo.list_celebrants([OCT_22])
        assert sorted(c.user_id for c in birthdays) == sorted([birthday, notice])
        assert [(c.user_id, c.years) for c in anniversaries] == [(twoyears, 2)]
        # Celebrants carry month/day only — never the birth year.
        assert {(c.month, c.day) for c in birthdays} == {(10, 22)}

        b_count, a_count = await repo.count_celebration_audience()
        # Audience = date on file, not muted, still here: Birthday, Notice,
        # Prejoin, Other (Muted, Exited, Inactive excluded).
        assert b_count == 4
        # Twoyears, Joiner, Prejoin have joining dates.
        assert a_count == 3


async def test_leap_day_people_are_celebrated_on_feb_28_in_common_years(
    pg_session_factory: Factory,
) -> None:
    org, (leap,), _ = await setup_org(pg_session_factory, "Leap")
    await _set_profile(
        pg_session_factory,
        leap,
        date_of_birth=date(1996, 2, 29),
        date_of_joining=date(2020, 2, 29),
    )
    async with pg_session_factory() as db:
        repo = EmployeeProfileRepository(db, org_id=org)
        birthdays, anniversaries = await repo.list_celebrants([date(2027, 2, 28)])
        assert [(c.month, c.day) for c in birthdays] == [(2, 29)]
        assert [c.years for c in anniversaries] == [7]
        # In a leap year they get their real day, not the 28th.
        birthdays, _ = await repo.list_celebrants([date(2028, 2, 28)])
        assert birthdays == []


async def test_members_shared_with_another_org_are_detected(
    pg_session_factory: Factory,
) -> None:
    org_a, (solo, shared), _ = await setup_org(pg_session_factory, "Solo", "Shared")
    async with pg_session_factory() as db:
        org_b = Organization(name=f"B {uuid.uuid4()}", slug=f"b-{uuid.uuid4().hex[:8]}")
        db.add(org_b)
        await db.flush()
        db.add(OrgToUser(user_id=shared, org_id=org_b.id))
        await db.commit()
    async with pg_session_factory() as db:
        assert await shared_member_ids(db, [solo, shared]) == {shared}


async def test_opt_out_is_the_employees_through_the_api(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (emp, hr), _ = await setup_org(pg_session_factory, "Emp", "Hr")
    await give_role(pg_session_factory, org, hr, "hr")
    url = f"/api/v1/employees/{emp}/celebrations"

    r = await client.patch(url, json={"celebrate_birthday": False}, headers=as_user(emp, org))
    assert r.status_code == 200
    assert r.json()["personal"]["celebrate_birthday"] is False

    # HR saving personal details with a stale form must not unmute.
    r = await client.put(
        f"/api/v1/employees/{emp}/personal",
        json={"blood_group": "o_positive", "celebrate_birthday": True},
        headers=as_user(hr, org),
    )
    assert r.status_code == 200
    assert r.json()["personal"]["celebrate_birthday"] is False

    r = await client.patch(url, json={"celebrate_birthday": True}, headers=as_user(hr, org))
    assert r.status_code == 403
    r = await client.patch(url, json={"celebrate_anniversary": False}, headers=as_user(hr, org))
    assert r.status_code == 200

    r = await client.patch(url, json={"celebrate_birthday": True}, headers=as_user(emp, org))
    assert r.json()["personal"]["celebrate_birthday"] is True


async def test_settings_changes_are_audited_and_channel_is_admin_only(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (admin, hr), _ = await setup_org(pg_session_factory, "Admin", "Hr")
    await give_role(pg_session_factory, org, admin, "admin")
    await give_role(pg_session_factory, org, hr, "hr")
    url = "/api/v1/settings/celebrations"
    settings = {
        "enabled": True,
        "slackChannelId": "C123",
        "timezone": "Europe/London",
        "postTime": "09:30",
    }

    r = await client.patch(url, json=settings, headers=as_user(admin, org))
    assert r.status_code == 200, r.text
    r = await client.patch(
        url, json={**settings, "slackChannelId": "CHR"}, headers=as_user(hr, org)
    )
    assert r.status_code == 403
    r = await client.patch(url, json={**settings, "postTime": "10:00"}, headers=as_user(hr, org))
    assert r.status_code == 200
    r = await client.patch(
        url, json={**settings, "postTime": "10:00", "timezone": None}, headers=as_user(hr, org)
    )
    assert r.status_code == 422  # a timezone is required while switched on

    async with pg_session_factory() as db:
        events = (
            await db.execute(
                select(CelebrationConfigEvent.action, CelebrationConfigEvent.actor_id)
                .where(CelebrationConfigEvent.org_id == org)
                .order_by(CelebrationConfigEvent.created_at)
            )
        ).all()
    assert [(e.action.value, e.actor_id) for e in events] == [
        ("enabled", admin),
        ("updated", hr),
    ]

    r = await client.get(f"{url}/history", headers=as_user(hr, org))
    assert r.status_code == 200 and r.json() == []
