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

"""The team calendar over HTTP: everyone sees who is out, few see why.

The leave type and reason reach only the requester, their direct
managers and HR. A skip-level boss and a peer see plain "leave".
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient

from app.services.leave.lifecycle import decide, submit
from tests.integration.leave_edge_support import freeze_today
from tests.integration.leave_support import NOBODY, Factory, as_user, leave_body, setup_org, team

pytestmark = pytest.mark.integration
CALENDAR = "/api/v1/leave/calendar"
TODAY = date(2030, 6, 3)  # a Monday
JUNE = {"start": "2030-06-01", "end": "2030-06-30"}


@pytest.fixture(autouse=True)
def _frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_today(monkeypatch, TODAY)


async def _book(
    factory: Factory,
    org: uuid.UUID,
    emp: uuid.UUID,
    type_id: uuid.UUID,
    day: date,
    approver: uuid.UUID | None,
) -> uuid.UUID:
    """A one-day request with a reason; approved by ``approver`` if given."""
    async with factory() as db:
        request, _ = await submit(db, org, emp, leave_body(type_id, day, day, reason="Fever"))
        if approver is not None:
            await decide(
                db,
                org_id=org,
                actor=approver,
                perms=NOBODY,
                request_id=request.id,
                approve=True,
                note=None,
            )
        await db.commit()
        return request.id


async def _entries(
    client: AsyncClient, org: uuid.UUID, viewer: uuid.UUID, params: dict[str, str] = JUNE
) -> list[dict[str, Any]]:
    response = await client.get(CALENDAR, params=params, headers=as_user(viewer, org))
    assert response.status_code == 200, response.text
    return list(response.json()["entries"])


async def test_type_and_reason_reach_only_the_requester_managers_and_hr(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    await _book(pg_session_factory, org, p["emp"], casual, date(2030, 6, 11), p["mgr"])
    seen = {who: await _entries(client, org, p[who]) for who in p}
    for who, entries in seen.items():
        assert [e["user"]["user_id"] for e in entries] == [str(p["emp"])], who
    for who in ("emp", "mgr", "hr"):
        entry = seen[who][0]
        assert entry["leave_type"]["name"] == "Casual" and entry["reason"] == "Fever", who
    for who in ("boss", "peer"):
        entry = seen[who][0]
        assert entry["leave_type"] is None and entry["reason"] is None, who
        assert entry["kind"] == "leave" and not entry["is_own"]
    assert seen["emp"][0]["is_own"]


async def test_pending_leave_shows_only_to_the_requester(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    request_id = await _book(pg_session_factory, org, p["emp"], casual, date(2030, 6, 12), None)
    own = await _entries(client, org, p["emp"])
    assert [(e["request_id"], e["status"]) for e in own] == [(str(request_id), "pending")]
    # Not even the manager who will decide it sees it on the calendar yet.
    for who in ("mgr", "hr", "peer"):
        assert await _entries(client, org, p[who]) == [], who


async def test_another_orgs_leave_never_shows(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    other, (stranger,), _ = await setup_org(pg_session_factory, "Stranger")
    await _book(pg_session_factory, org, p["emp"], casual, date(2030, 6, 13), p["mgr"])
    assert await _entries(client, other, stranger) == []


@pytest.mark.parametrize(
    ("start", "end", "status"),
    [
        ("2030-06-30", "2030-06-01", 422),  # ends before it starts
        ("2030-06-01", "2030-09-03", 422),  # 94 days apart
        ("2030-06-01", "2030-09-02", 200),  # exactly 93 days apart
        ("2030-06-11", "2030-06-11", 200),  # a single day
    ],
)
async def test_the_range_is_one_day_to_93_days(
    client: AsyncClient, pg_session_factory: Factory, start: str, end: str, status: int
) -> None:
    org, (viewer,), _ = await setup_org(pg_session_factory, "Viewer")
    response = await client.get(
        CALENDAR, params={"start": start, "end": end}, headers=as_user(viewer, org)
    )
    assert response.status_code == status, response.text
