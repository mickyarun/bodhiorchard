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

"""Concurrent submits and decisions, and balances changing under a request.

These run the real lock and conditional updates against Postgres with
separate sessions, so two callers genuinely race.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest

from app.api.v1._leave_errors import status_for
from app.models.leave_ledger import LeaveLedgerEntry, LedgerEntryType
from app.models.leave_request import LeaveRequest, LeaveStatus
from app.schemas.leave import LeaveRequestCreate
from app.services.leave import cancellation
from app.services.leave.cancellation import cancel
from app.services.leave.errors import LeaveError
from app.services.leave.lifecycle import decide, submit
from app.services.leave.summary import build_summary
from tests.integration.leave_support import (
    NOBODY,
    Factory,
    future_monday,
    leave_body,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration


async def _try_submit(
    factory: Factory, org: uuid.UUID, user: uuid.UUID, body: LeaveRequestCreate
) -> int:
    async with factory() as db:
        try:
            await submit(db, org, user, body)
            await db.commit()
            return 201
        except LeaveError as exc:
            await db.rollback()
            return status_for(exc)


async def _try_decide(
    factory: Factory, org: uuid.UUID, actor: uuid.UUID, request_id: uuid.UUID, approve: bool
) -> int:
    async with factory() as db:
        try:
            await decide(
                db,
                org_id=org,
                actor=actor,
                perms=NOBODY,
                request_id=request_id,
                approve=approve,
                note=None if approve else "Team is short that week",
            )
            await db.commit()
            return 200
        except LeaveError as exc:
            await db.rollback()
            return status_for(exc)


async def _available(factory: Factory, org: uuid.UUID, user: uuid.UUID) -> Decimal | None:
    async with factory() as db:
        summary = await build_summary(db, org, user, None)
        return summary.balances[0].available


async def _lop_days(factory: Factory, request_id: uuid.UUID) -> Decimal:
    async with factory() as db:
        request = await db.get(LeaveRequest, request_id)
        assert request is not None
        return request.lop_days


async def test_parallel_submits_cannot_overspend(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    week1 = future_monday()
    week2 = week1 + timedelta(weeks=1)
    # 3 + 3 days against a quota of 5: whichever is priced second takes
    # one day as loss of pay, never both paid in full.
    results = await asyncio.gather(
        _try_submit(pg_session_factory, org, emp, leave_body(casual, week1, week1 + timedelta(2))),
        _try_submit(pg_session_factory, org, emp, leave_body(casual, week2, week2 + timedelta(2))),
    )
    assert results == [201, 201]
    assert await _available(pg_session_factory, org, emp) == Decimal("0")
    async with pg_session_factory() as db:
        summary = await build_summary(db, org, emp, None)
    assert summary.lop_days == Decimal("1")


async def test_two_managers_deciding_at_once_make_one_decision(
    pg_session_factory: Factory,
) -> None:
    org, (emp, m1, m2), casual = await setup_org(pg_session_factory, "Emp", "M1", "M2")
    await report_to(pg_session_factory, org, emp, m1, m2)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon))
        await db.commit()
    results = await asyncio.gather(
        _try_decide(pg_session_factory, org, m1, request.id, True),
        _try_decide(pg_session_factory, org, m2, request.id, False),
    )
    assert sorted(results) == [200, 409]


async def test_approval_reprices_once_hr_cut_the_balance(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon + timedelta(2)))
        db.add(
            LeaveLedgerEntry(
                org_id=org,
                user_id=emp,
                leave_type_id=casual,
                leave_year=mon.year,
                entry_type=LedgerEntryType.ADJUSTMENT,
                days=Decimal("-3"),
                note="Correction",
            )
        )
        await db.commit()
    # 2 days are left for a 3-day request: the third is loss of pay.
    assert await _try_decide(pg_session_factory, org, mgr, request.id, True) == 200
    assert await _lop_days(pg_session_factory, request.id) == Decimal("1")


async def test_cancelling_leave_under_way_keeps_the_days_taken(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon + timedelta(4)))
        await decide(
            db, org_id=org, actor=mgr, perms=NOBODY, request_id=request.id, approve=True, note=None
        )
        await db.commit()
    wednesday = mon + timedelta(2)
    monkeypatch.setattr(cancellation, "today_for", lambda _policy: wednesday)
    async with pg_session_factory() as db:
        cut = await cancel(db, org, emp, request.id)
        await db.commit()
    assert (cut.status, cut.end_date, cut.days) == (
        LeaveStatus.APPROVED,
        mon + timedelta(1),
        Decimal("2"),
    )
    assert await _available(pg_session_factory, org, emp) == Decimal("3")


async def test_finished_leave_cannot_be_cancelled(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon))
        await decide(
            db, org_id=org, actor=mgr, perms=NOBODY, request_id=request.id, approve=True, note=None
        )
        await db.commit()
    monkeypatch.setattr(cancellation, "today_for", lambda _policy: mon + timedelta(days=3))
    async with pg_session_factory() as db:
        with pytest.raises(LeaveError) as excinfo:
            await cancel(db, org, emp, request.id)
    assert status_for(excinfo.value) == 409


async def test_an_aged_request_is_still_repriced_on_approval(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon + timedelta(2)))
        db.add(
            LeaveLedgerEntry(
                org_id=org,
                user_id=emp,
                leave_type_id=casual,
                leave_year=mon.year,
                entry_type=LedgerEntryType.ADJUSTMENT,
                days=Decimal("-3"),
                note="Correction",
            )
        )
        await db.commit()
    # Weeks later the request is past the backdating limit, still pending.
    monkeypatch.setattr(
        "app.services.leave.evaluation.today_for", lambda _p: mon + timedelta(days=30)
    )
    assert await _try_decide(pg_session_factory, org, mgr, request.id, True) == 200
    assert await _lop_days(pg_session_factory, request.id) == Decimal("1")
