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

"""Who cannot reach sensitive details and documents, and what a reveal returns.

Complements ``test_employee_sensitive.py`` (HR, self and a developer) with the
reporting manager, HR of another org, bad field names and cleared values.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.employee_audit_event import EmployeeAuditEvent
from app.models.notification import Notification, NotificationType
from tests.integration.gamification_support import join_org
from tests.integration.hr_support import PEOPLE as BASE
from tests.integration.hr_support import configure_hr_storage, seed_employee
from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration
Seeded = tuple[uuid.UUID, dict[str, uuid.UUID]]


@pytest_asyncio.fixture
async def seeded(
    client: AsyncClient,
    pg_session_factory: Factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> AsyncIterator[Seeded]:
    """The seeded employee record; HR deletes its document afterwards."""
    configure_hr_storage(monkeypatch, tmp_path)
    org, people = await seed_employee(client, pg_session_factory)
    yield org, people
    removed = await client.delete(
        f"{BASE}/documents/{people['doc']}", headers=as_user(people["hr"], org)
    )
    assert removed.status_code == 204


async def _audit_count(factory: Factory, subject: uuid.UUID) -> int:
    async with factory() as db:
        count = await db.scalar(
            select(func.count()).where(EmployeeAuditEvent.subject_user_id == subject)
        )
        return int(count or 0)


async def _probe(
    client: AsyncClient, emp: uuid.UUID, doc: uuid.UUID, headers: dict[str, str]
) -> list[int]:
    """Status codes for every read of someone's sensitive record."""
    return [
        (await client.get(f"{BASE}/{emp}/sensitive", headers=headers)).status_code,
        (
            await client.post(
                f"{BASE}/{emp}/sensitive/reveal", json={"field": "pan"}, headers=headers
            )
        ).status_code,
        (await client.get(f"{BASE}/{emp}/access-log", headers=headers)).status_code,
        (await client.get(f"{BASE}/{emp}/documents", headers=headers)).status_code,
        (await client.get(f"{BASE}/documents/{doc}/content", headers=headers)).status_code,
        (await client.delete(f"{BASE}/documents/{doc}", headers=headers)).status_code,
    ]


async def test_a_reporting_manager_cannot_see_or_reveal_anything(
    client: AsyncClient, pg_session_factory: Factory, seeded: Seeded
) -> None:
    """Managing someone grants no access to their IDs, bank details or documents."""
    org, p = seeded
    before = await _audit_count(pg_session_factory, p["emp"])
    statuses = await _probe(client, p["emp"], p["doc"], as_user(p["mgr"], org))
    assert statuses == [403] * 6
    assert await _audit_count(pg_session_factory, p["emp"]) == before


async def test_hr_of_another_org_finds_nothing_and_leaves_no_trace(
    client: AsyncClient, pg_session_factory: Factory, seeded: Seeded
) -> None:
    """Even when the employee is also a member there, another org's HR gets 404s."""
    org, p = seeded
    other, (other_hr,), _ = await setup_org(pg_session_factory, "OtherHr")
    await give_role(pg_session_factory, other, other_hr, "hr")
    await join_org(pg_session_factory, other, p["emp"])
    before = await _audit_count(pg_session_factory, p["emp"])
    statuses = await _probe(client, p["emp"], p["doc"], as_user(other_hr, other))
    assert statuses == [404] * 6
    assert await _audit_count(pg_session_factory, p["emp"]) == before
    still_there = await client.get(f"{BASE}/{p['emp']}/documents", headers=as_user(p["hr"], org))
    assert [d["id"] for d in still_there.json()["documents"]] == [str(p["doc"])]


async def test_only_encrypted_fields_can_be_revealed(
    client: AsyncClient, pg_session_factory: Factory, seeded: Seeded
) -> None:
    """A plain or made-up field name is a 422 and is not logged as a reveal."""
    org, p = seeded
    before = await _audit_count(pg_session_factory, p["emp"])
    for field in ("bank_ifsc", "password", ""):
        response = await client.post(
            f"{BASE}/{p['emp']}/sensitive/reveal",
            json={"field": field},
            headers=as_user(p["hr"], org),
        )
        assert response.status_code == 422, field
    assert await _audit_count(pg_session_factory, p["emp"]) == before


async def test_a_cleared_value_is_unset_and_its_reveal_is_still_logged(
    client: AsyncClient, pg_session_factory: Factory, seeded: Seeded
) -> None:
    """Saving "" clears the PAN; revealing it returns null but is on record."""
    org, p = seeded
    hr = as_user(p["hr"], org)
    cleared = await client.put(f"{BASE}/{p['emp']}/sensitive", json={"pan": ""}, headers=hr)
    assert cleared.json()["pan"] == {"is_set": False, "last4": None}
    revealed = await client.post(
        f"{BASE}/{p['emp']}/sensitive/reveal", json={"field": "pan"}, headers=hr
    )
    assert revealed.json() == {"field": "pan", "value": None}
    log = (await client.get(f"{BASE}/{p['emp']}/access-log", headers=hr)).json()
    assert [(e["action"], e["target"]) for e in log][:2] == [
        ("field_revealed", "pan"),
        ("details_updated", "pan"),
    ]


async def test_an_address_in_any_script_round_trips_without_alerting(
    client: AsyncClient, pg_session_factory: Factory, seeded: Seeded
) -> None:
    """Unicode survives encryption; address changes do not alert the employee."""
    org, p = seeded
    hr = as_user(p["hr"], org)
    address = "12, Anna Salai — சென்னை 600002 ✓"
    saved = await client.put(
        f"{BASE}/{p['emp']}/sensitive", json={"current_address": address}, headers=hr
    )
    assert saved.json()["current_address"] == {"is_set": True, "last4": None}
    assert address not in saved.text
    revealed = await client.post(
        f"{BASE}/{p['emp']}/sensitive/reveal", json={"field": "current_address"}, headers=hr
    )
    assert revealed.json()["value"] == address
    async with pg_session_factory() as db:
        alerts = await db.scalar(
            select(func.count()).where(
                Notification.user_id == p["emp"],
                Notification.type == NotificationType.EMPLOYEE_RECORD_CHANGED,
            )
        )
    assert alerts == 1  # the PAN saved during setup, not the address


async def test_a_badly_formed_id_is_refused_and_nothing_changes(
    client: AsyncClient, pg_session_factory: Factory, seeded: Seeded
) -> None:
    """A PAN in the wrong shape is a 422 and the saved one stays."""
    org, p = seeded
    hr = as_user(p["hr"], org)
    bad = await client.put(f"{BASE}/{p['emp']}/sensitive", json={"pan": "12345"}, headers=hr)
    assert bad.status_code == 422
    current = await client.get(f"{BASE}/{p['emp']}/sensitive", headers=hr)
    assert current.json()["pan"] == {"is_set": True, "last4": "234F"}
