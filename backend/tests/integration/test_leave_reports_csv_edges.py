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

"""Leave report exports over HTTP: hostile text stays text, empty ranges stay empty."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.leave_ledger import LeaveLedgerEntry, LedgerEntryType
from app.models.leave_type import LeaveType
from app.models.user import User
from app.repositories.employee_profile import EmployeeProfileRepository
from tests.integration.leave_edge_support import freeze_today
from tests.integration.leave_support import Factory, add_request, as_user, team

pytestmark = pytest.mark.integration
REPORTS = "/api/v1/leave/reports"
JUNE = {"start": "2026-06-01", "end": "2026-06-30"}
EVIL_NAME = '=HYPERLINK("http://evil.example","open")'


@pytest.fixture(autouse=True)
def _frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_today(monkeypatch, date(2026, 7, 6))


async def _make_hostile(
    factory: Factory, org: uuid.UUID, emp: uuid.UUID, mgr: uuid.UUID, type_id: uuid.UUID
) -> None:
    """Names, department and type name that a spreadsheet would run as formulas."""
    async with factory() as db:
        for user_id, name in ((emp, EVIL_NAME), (mgr, "-Mallory")):
            user = await db.get(User, user_id)
            assert user is not None
            user.name = name
        profile = await EmployeeProfileRepository(db, org_id=org).get_by_user(emp)
        assert profile is not None
        profile.department = "@SUM(A1:A9)"
        leave_type = await db.get(LeaveType, type_id)
        assert leave_type is not None
        leave_type.name = "+cmd|' /C calc'!A0"
        db.add(
            LeaveLedgerEntry(
                org_id=org, user_id=emp, leave_type_id=type_id, leave_year=2026,
                entry_type=LedgerEntryType.ADJUSTMENT, days=Decimal("-2"), note="Fix",
            )
        )  # fmt: skip
        await db.commit()


async def _csv(
    client: AsyncClient, path: str, params: dict[str, str], headers: dict[str, str]
) -> list[list[str]]:
    response = await client.get(f"{REPORTS}/{path}", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


async def test_text_cells_and_headers_never_become_formulas(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    await add_request(
        pg_session_factory, org, p["emp"], date(2026, 6, 2), date(2026, 6, 2), "1",
        type_id=casual, decided_by=p["mgr"],
    )  # fmt: skip
    await _make_hostile(pg_session_factory, org, p["emp"], p["mgr"], casual)
    hr = as_user(p["hr"], org)

    header, *rows = await _csv(client, "register.csv", JUNE, hr)
    (row,) = rows
    cells = dict(zip(header, row, strict=True))
    assert cells["Employee"] == "'" + EVIL_NAME
    assert cells["Department"] == "'@SUM(A1:A9)"
    assert cells["Leave type"] == "'+cmd|' /C calc'!A0"
    assert cells["Decided by"] == "'-Mallory"
    assert (cells["From"], Decimal(cells["Days"])) == ("2026-06-02", 1)

    summary_header, *_ = await _csv(client, "summary.csv", JUNE, hr)
    assert "'+cmd|' /C calc'!A0 taken" in summary_header

    header, *rows = await _csv(client, "balances.csv", {"year": "2026"}, hr)
    mine = next(dict(zip(header, r, strict=True)) for r in rows if r[0] == "'" + EVIL_NAME)
    # A negative number is a value, not text to neutralise.
    assert Decimal(mine["Adjustments"]) == Decimal("-2")


async def test_a_range_with_no_leave_exports_just_the_header(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    await add_request(
        pg_session_factory, org, p["emp"], date(2026, 6, 2), date(2026, 6, 2), "1", type_id=casual
    )
    hr = as_user(p["hr"], org)
    july = {"start": "2026-07-01", "end": "2026-07-31"}
    register = await client.get(f"{REPORTS}/register", params=july, headers=hr)
    assert register.status_code == 200 and register.json()["rows"] == []
    rows = await _csv(client, "register.csv", july, hr)
    assert len(rows) == 1 and rows[0][0] == "Employee"
    # The summary still lists everyone, with nothing taken.
    summary = (await client.get(f"{REPORTS}/summary", params=july, headers=hr)).json()
    assert summary["rows"] and all(Decimal(r["leave_days"]) == 0 for r in summary["rows"])


@pytest.mark.parametrize(
    ("start", "end", "status"),
    [
        ("2026-06-02", "2026-06-02", 200),  # a single day
        ("2026-01-01", "2027-01-01", 200),  # 365 days apart
        ("2028-01-01", "2028-12-31", 200),  # a whole leap year, 365 days apart
        ("2026-01-01", "2027-01-02", 422),  # 366 days apart
        ("2026-06-03", "2026-06-02", 422),  # ends before it starts
    ],
)
async def test_a_report_range_is_one_day_to_a_year(
    client: AsyncClient, pg_session_factory: Factory, start: str, end: str, status: int
) -> None:
    org, p, _ = await team(pg_session_factory)
    for path in ("register", "register.csv"):
        response = await client.get(
            f"{REPORTS}/{path}",
            params={"start": start, "end": end},
            headers=as_user(p["hr"], org),
        )
        assert response.status_code == status, (path, response.text)
