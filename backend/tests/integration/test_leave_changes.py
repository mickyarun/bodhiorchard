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

"""Managers, HR and the owner change approved leave until it's over; the requester is told."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.leave_request import LeaveRequest, LeaveStatus
from app.models.notification import Notification
from tests.integration.leave_support import Factory, add_request, as_user, future_monday, team

pytestmark = pytest.mark.integration


async def _approved(
    client: AsyncClient, org: uuid.UUID, emp: uuid.UUID, mgr: uuid.UUID, casual: uuid.UUID,
    start: date, end: date,
) -> str:  # fmt: skip
    body = {"kind": "leave", "leave_type_id": str(casual), "start_date": start.isoformat(),
            "end_date": end.isoformat()}  # fmt: skip
    made = await client.post("/api/v1/leave/requests", json=body, headers=as_user(emp, org))
    assert made.status_code == 201, made.text
    request_id = str(made.json()["id"])
    ok = await client.post(
        f"/api/v1/leave/requests/{request_id}/approve", json={}, headers=as_user(mgr, org)
    )
    assert ok.status_code == 200, ok.text
    return request_id


async def _notes_for(factory: Factory, user: uuid.UUID) -> list[str]:
    async with factory() as db:
        rows = await db.scalars(select(Notification.title).where(Notification.user_id == user))
        return list(rows)


async def test_manager_withdraws_upcoming_leave_and_the_employee_is_told(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    monday = future_monday()
    rid = await _approved(client, org, p["emp"], p["mgr"], casual, monday, monday + timedelta(1))

    no_note = await client.post(
        f"/api/v1/leave/requests/{rid}/withdraw", json={}, headers=as_user(p["mgr"], org)
    )
    assert no_note.status_code == 422
    done = await client.post(
        f"/api/v1/leave/requests/{rid}/withdraw",
        json={"note": "Release week, sorry"},
        headers=as_user(p["mgr"], org),
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "rejected"
    assert done.json()["can_change"] is False
    assert "Approval withdrawn" in await _notes_for(pg_session_factory, p["emp"])
    # The 2 days are back on the balance: they can book all 5 again.
    again = await client.post(
        "/api/v1/leave/requests/preview",
        json={
            "kind": "leave",
            "leave_type_id": str(casual),
            "start_date": (monday + timedelta(7)).isoformat(),
            "end_date": (monday + timedelta(11)).isoformat(),
        },  # fmt: skip
        headers=as_user(p["emp"], org),
    )
    assert float(again.json()["lop_days"]) == 0


async def test_manager_moves_leave_and_a_clash_changes_nothing(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    monday = future_monday()
    rid = await _approved(client, org, p["emp"], p["mgr"], casual, monday, monday + timedelta(1))
    other = await _approved(
        client, org, p["emp"], p["mgr"], casual, monday + timedelta(7), monday + timedelta(7)
    )
    headers = as_user(p["mgr"], org)

    clash = await client.post(
        f"/api/v1/leave/requests/{rid}/reschedule",
        json={
            "start_date": (monday + timedelta(7)).isoformat(),
            "end_date": (monday + timedelta(8)).isoformat(),
        },  # fmt: skip
        headers=headers,
    )
    assert clash.status_code == 409, clash.text
    async with pg_session_factory() as db:
        kept = await db.get(LeaveRequest, uuid.UUID(rid))
        assert kept is not None and kept.status == LeaveStatus.APPROVED
        assert kept.start_date == monday  # the set-aside rolled back

    moved = await client.post(
        f"/api/v1/leave/requests/{rid}/reschedule",
        json={
            "start_date": (monday + timedelta(2)).isoformat(),
            "end_date": (monday + timedelta(4)).isoformat(),
            "note": "Swap with Ravi",
        },  # fmt: skip
        headers=headers,
    )
    assert moved.status_code == 200, moved.text
    body = moved.json()
    assert body["status"] == "approved"
    assert body["start_date"] == (monday + timedelta(2)).isoformat()
    assert float(body["days"]) == 3
    assert body["decision_note"] == "Swap with Ravi" and body["can_change"] is True
    assert "Leave changed" in await _notes_for(pg_session_factory, p["emp"])
    assert other  # untouched


async def test_only_their_approvers_and_never_their_own(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    monday = future_monday()
    rid = await _approved(client, org, p["emp"], p["mgr"], casual, monday, monday)
    note = {"note": "no"}
    for who in ("emp", "peer"):
        tried = await client.post(
            f"/api/v1/leave/requests/{rid}/withdraw", json=note, headers=as_user(p[who], org)
        )
        assert tried.status_code == 403, (who, tried.text)
    # The decided tab offers it to the manager who can change it.
    page = await client.get(
        "/api/v1/leave/approvals", params={"status": "decided"}, headers=as_user(p["mgr"], org)
    )
    mine = [i for i in page.json()["items"] if i["request"]["id"] == rid]
    assert mine and mine[0]["request"]["can_change"] is True


async def test_leave_nobody_had_to_approve_can_still_be_changed(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    monday = future_monday()
    # Approved automatically (no decider), like auto WFH or period leave.
    await add_request(
        pg_session_factory, org, p["emp"], monday, monday, "1", type_id=casual,
        decided_at=datetime.now(UTC),
    )  # fmt: skip
    page = await client.get(
        "/api/v1/leave/approvals", params={"status": "decided"}, headers=as_user(p["mgr"], org)
    )
    ours = [i for i in page.json()["items"] if i["request"]["user"]["user_id"] == str(p["emp"])]
    assert ours and ours[0]["request"]["can_change"] is True
