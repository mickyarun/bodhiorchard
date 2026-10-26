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

"""Linking existing types to the library: by hand, and the reviewed bulk link."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.leave_type import LeaveAccrual, LeaveType
from app.repositories.leave_type_template import LeaveTypeTemplateRepository
from app.services.leave.lifecycle import submit
from app.services.leave.policies import ensure_default_policy
from app.services.leave.type_link_apply import Acceptance, LinkStatus, link_existing_types
from tests.integration.leave_library_support import add_policy, library_sick
from tests.integration.leave_support import (
    Factory,
    as_user,
    future_monday,
    give_role,
    leave_body,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration
D = Decimal
BASE = "/api/v1/leave"


async def _type(factory: Factory, org: uuid.UUID, policy: uuid.UUID, name: str, code: str,
                quota: str | None, **rules: object) -> uuid.UUID:  # fmt: skip
    async with factory() as db:
        days = None if quota is None else D(quota)
        row = LeaveType(org_id=org, policy_id=policy, name=name, code=code,
                        annual_quota_days=days, **rules)  # fmt: skip
        db.add(row)
        await db.commit()
        return row.id


async def test_a_policy_type_links_and_lets_go_keeping_its_requests(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (hr, emp), _casual = await setup_org(pg_session_factory, "Hr", "Emp")
    await give_role(pg_session_factory, org, hr, "hr")
    auth = as_user(hr, org)
    async with pg_session_factory() as db:
        policy = (await ensure_default_policy(db, org)).id
    sick = await _type(pg_session_factory, org, policy, "Sick leave", "SL", "6")
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(sick, mon, mon))
        await db.commit()
    entry = await library_sick(client, auth)
    url = f"{BASE}/types/{sick}/link"
    linked = await client.post(url, json={"template_id": entry}, headers=auth)
    assert linked.status_code == 200, linked.text
    assert (linked.json()["id"], linked.json()["name"]) == (str(sick), "Sick")
    assert D(linked.json()["annual_quota_days"]) == D(4)
    assert request.leave_type_id == sick

    unlinked = await client.delete(url, headers=auth)
    assert unlinked.status_code == 200, unlinked.text
    assert (unlinked.json()["template_id"], unlinked.json()["name"]) == (None, "Sick")
    edit = {"name": "Sick", "code": "SL", "annual_quota_days": "5"}
    assert (await client.put(f"{BASE}/types/{sick}", json=edit, headers=auth)).status_code == 200


async def test_linking_a_switched_off_type_keeps_it_off(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (hr,), _casual = await setup_org(pg_session_factory, "Hr")
    await give_role(pg_session_factory, org, hr, "hr")
    async with pg_session_factory() as db:
        policy = (await ensure_default_policy(db, org)).id
    retired = await _type(pg_session_factory, org, policy, "Sick", "SL", "4", is_active=False)
    entry = await library_sick(client, as_user(hr, org))
    linked = await client.post(
        f"{BASE}/types/{retired}/link", json={"template_id": entry}, headers=as_user(hr, org)
    )
    assert linked.status_code == 200, linked.text
    assert (linked.json()["template_id"], linked.json()["is_active"]) == (entry, False)


async def _two_policies(
    factory: Factory,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Org, HR, an employee reporting to HR, the default policy and a UK one."""
    org, (hr, emp), _casual = await setup_org(factory, "Hr", "Emp")
    await report_to(factory, org, emp, hr)
    async with factory() as db:
        india = (await ensure_default_policy(db, org)).id
    uk = await add_policy(factory, org, hr, "UK Shift")
    return org, hr, emp, india, uk


async def test_dry_run_reports_and_changes_nothing_then_apply_waits_for_confirmation(
    pg_session_factory: Factory,
) -> None:
    org, hr, _emp, india, uk = await _two_policies(pg_session_factory)
    await _type(pg_session_factory, org, india, "Sick leave", "SL", "4")
    uk_sick = await _type(pg_session_factory, org, uk, "Sick leave", "SL", "6")
    await _type(pg_session_factory, org, india, "Earned leave", "EL", "12")
    await _type(pg_session_factory, org, uk, "Earned Leave", "EL", "12", is_encashable=True)
    await _type(pg_session_factory, org, uk, "Only here", "OH", "1")

    async with pg_session_factory() as db:
        dry = await link_existing_types(db, org, hr, apply=False)
    by_name = {o.group.name: o for o in dry}
    assert set(by_name) == {"Earned leave", "Sick leave"}
    # The same groups wait for confirmation as when applying.
    assert {name: o.status for name, o in by_name.items()} == {
        "Earned leave": LinkStatus.NEEDS_CONFIRMATION, "Sick leave": LinkStatus.READY
    }  # fmt: skip
    earned, sick = by_name["Earned leave"].group, by_name["Sick leave"].group
    assert [m.differences for m in earned.members] == [
        {}, {"name": ["Earned Leave", "Earned leave"], "is_encashable": [True, False]}
    ]  # fmt: skip
    assert [(m.policy_name, m.own_quota) for m in sick.members] == [
        ("Default", False), ("UK Shift", True)
    ]  # fmt: skip
    async with pg_session_factory() as db:
        assert await LeaveTypeTemplateRepository(db, org_id=org).list_by_name() == []

    async with pg_session_factory() as db:
        applied = await link_existing_types(db, org, hr, apply=True)
    assert {o.group.name: o.status for o in applied} == {
        "Earned leave": LinkStatus.NEEDS_CONFIRMATION, "Sick leave": LinkStatus.LINKED
    }  # fmt: skip
    async with pg_session_factory() as db:
        row = await db.get(LeaveType, uk_sick)
        assert row is not None and row.template_id is not None
        assert (row.own_quota, row.annual_quota_days, row.name) == (True, D(6), "Sick leave")
        # Confirmed by name, whatever its case or spacing.
        accepted = await link_existing_types(
            db, org, hr, apply=True, accepted=Acceptance(names=frozenset({"earned  LEAVE"}))
        )
    assert [(o.group.name, o.status) for o in accepted] == [("Earned leave", LinkStatus.LINKED)]
    async with pg_session_factory() as db:
        everything = Acceptance(everything=True)
        assert await link_existing_types(db, org, hr, apply=True, accepted=everything) == []


async def test_a_policy_whose_year_is_allocated_blocks_an_accrual_change(
    pg_session_factory: Factory,
) -> None:
    org, hr, emp, india, uk = await _two_policies(pg_session_factory)
    await _type(pg_session_factory, org, uk, "Earned", "EL", "12", accrual=LeaveAccrual.MONTHLY)
    in_use = await _type(pg_session_factory, org, india, "Earned", "EL", "12")
    async with pg_session_factory() as db:
        policy = await ensure_default_policy(db, org)
        policy.created_at = policy.created_at.replace(year=policy.created_at.year + 1)
        mon = future_monday()
        await submit(db, org, emp, leave_body(in_use, mon, mon))
        await db.commit()
    async with pg_session_factory() as db:
        dry = await link_existing_types(db, org, hr, apply=False)
    assert [o.status for o in dry] == [LinkStatus.BLOCKED]
    assert dry[0].reason.startswith("On Default: This type is already in use this leave year")
