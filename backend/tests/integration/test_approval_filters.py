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

"""Approvals queue filters: dates, kind, type and person narrow; the count doesn't."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient

from app.models.leave_request import LeaveKind, LeaveStatus
from app.services.leave import approvals_view
from tests.integration.leave_support import (
    Factory,
    add_request,
    as_user,
    give_role,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration
QUEUE = "/api/v1/leave/approvals"


async def names(client: AsyncClient, headers: dict[str, str], **params: str) -> list[str]:
    r = await client.get(QUEUE, params=params, headers=headers)
    assert r.status_code == 200, r.text
    return sorted(item["request"]["user"]["name"] for item in r.json()["items"])


async def test_filters_narrow_the_queue_but_not_the_count(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (hr_id, mgr, emp, peer), casual = await setup_org(
        pg_session_factory, "Hr", "Mgr", "Emp", "Peer"
    )
    await give_role(pg_session_factory, org, hr_id, "hr")
    await report_to(pg_session_factory, org, emp, mgr)
    pending = LeaveStatus.PENDING
    await add_request(
        pg_session_factory, org, emp, date(2030, 3, 4), date(2030, 3, 4), "1",
        type_id=casual, status=pending,
    )  # fmt: skip
    await add_request(
        pg_session_factory, org, peer, date(2030, 4, 1), date(2030, 4, 1), "1",
        kind=LeaveKind.WFH, status=pending,
    )  # fmt: skip
    hr = as_user(hr_id, org)
    assert await names(client, hr) == ["Emp", "Peer"]
    assert await names(client, hr, start="2030-03-01", end="2030-03-31") == ["Emp"]
    assert await names(client, hr, kind="wfh") == ["Peer"]
    assert await names(client, hr, leave_type_id=str(casual)) == ["Emp"]
    assert await names(client, hr, user_id=str(peer)) == ["Peer"]
    # A manager filtering on someone outside their team sees nothing.
    assert await names(client, as_user(mgr, org), user_id=str(peer)) == []
    count = await client.get(f"{QUEUE}/count", params={"kind": "wfh"}, headers=hr)
    assert count.json()["pending"] == 2
    bad = await client.get(QUEUE, params={"start": "2030-03-31", "end": "2030-03-01"}, headers=hr)
    assert bad.status_code == 422


async def test_a_date_range_reaches_decisions_older_than_90_days(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (hr_id, emp), casual = await setup_org(pg_session_factory, "Hr", "Emp")
    await give_role(pg_session_factory, org, hr_id, "hr")
    await add_request(
        pg_session_factory, org, emp, date(2024, 1, 8), date(2024, 1, 8), "1", type_id=casual,
        decided_by=hr_id, decided_at=datetime(2024, 1, 5, tzinfo=UTC),
    )  # fmt: skip
    hr = as_user(hr_id, org)
    assert await names(client, hr, status="decided") == []
    dated = {"status": "decided", "start": "2024-01-01", "end": "2024-01-31"}
    assert await names(client, hr, **dated) == ["Emp"]


async def test_the_decided_list_says_when_older_decisions_were_cut(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, (hr_id, emp, mgr), casual = await setup_org(pg_session_factory, "Hr", "Emp", "Mgr")
    await give_role(pg_session_factory, org, hr_id, "hr")
    await report_to(pg_session_factory, org, emp, mgr)
    for day in (5, 6):
        await add_request(
            pg_session_factory, org, emp, date(2030, 1, day), date(2030, 1, day), "1",
            type_id=casual, decided_by=hr_id, decided_at=datetime(2030, 1, 1, tzinfo=UTC),
        )  # fmt: skip
    dated = {"status": "decided", "start": "2030-01-01", "end": "2030-01-31"}
    hr = as_user(hr_id, org)
    monkeypatch.setattr(approvals_view, "DECIDED_LIMIT", 2)
    assert (await client.get(QUEUE, params=dated, headers=hr)).json()["truncated"] is True
    monkeypatch.setattr(approvals_view, "DECIDED_LIMIT", 3)
    assert (await client.get(QUEUE, params=dated, headers=hr)).json()["truncated"] is False
    # Only someone with reports can see reports on them.
    counts = {
        who: (await client.get(f"{QUEUE}/count", headers=as_user(who, org))).json()["has_reports"]
        for who in (hr_id, mgr, emp)
    }
    assert counts == {hr_id: False, mgr: True, emp: False}
