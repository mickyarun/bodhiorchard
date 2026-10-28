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

"""Decisions that race each other or the requester: exactly one outcome sticks.

Each caller has its own session, so the member lock and the conditional
status update are what keep the outcome single. "Today" is frozen.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.api.v1._leave_errors import status_for
from app.models.leave_request import LeaveStatus
from app.services.leave.cancellation import cancel
from app.services.leave.errors import LeaveError
from app.services.leave.lifecycle import decide, submit
from tests.integration.leave_edge_support import days_left, freeze_today, stored
from tests.integration.leave_support import NOBODY, Factory, leave_body, report_to, setup_org

pytestmark = pytest.mark.integration
TODAY = date(2030, 6, 3)  # a Monday
MON, WED = date(2030, 6, 10), date(2030, 6, 12)


@pytest.fixture(autouse=True)
def _frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_today(monkeypatch, TODAY)


async def _pending(
    factory: Factory, org: uuid.UUID, emp: uuid.UUID, casual: uuid.UUID
) -> uuid.UUID:
    async with factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, MON, WED))
        await db.commit()
        assert request.status == LeaveStatus.PENDING and request.days == Decimal(3)
        return request.id


async def _decide(
    factory: Factory, org: uuid.UUID, actor: uuid.UUID, request_id: uuid.UUID, note: str | None
) -> int:
    """Approve when ``note`` is None, else reject with it; returns the HTTP status."""
    async with factory() as db:
        try:
            await decide(
                db,
                org_id=org,
                actor=actor,
                perms=NOBODY,
                request_id=request_id,
                approve=note is None,
                note=note,
            )
            await db.commit()
            return 200
        except LeaveError as exc:
            await db.rollback()
            return status_for(exc)


async def _cancel(
    factory: Factory, org: uuid.UUID, actor: uuid.UUID, request_id: uuid.UUID
) -> int:
    async with factory() as db:
        try:
            await cancel(db, org, actor, request_id)
            await db.commit()
            return 200
        except LeaveError as exc:
            await db.rollback()
            return status_for(exc)


async def test_two_managers_approving_at_once_approve_once(pg_session_factory: Factory) -> None:
    org, (emp, m1, m2), casual = await setup_org(pg_session_factory, "Emp", "M1", "M2")
    await report_to(pg_session_factory, org, emp, m1, m2)
    request_id = await _pending(pg_session_factory, org, emp, casual)
    results = await asyncio.gather(
        _decide(pg_session_factory, org, m1, request_id, None),
        _decide(pg_session_factory, org, m2, request_id, None),
    )
    assert sorted(results) == [200, 409]
    winner = m1 if results[0] == 200 else m2
    request = await stored(pg_session_factory, request_id)
    assert (request.status, request.decided_by, request.lop_days) == (
        LeaveStatus.APPROVED,
        winner,
        Decimal(0),
    )
    # The 3 days are spent once, not twice.
    assert await days_left(pg_session_factory, org, emp, 2030) == (Decimal(2), Decimal(0))


async def test_two_rejections_at_once_keep_one_note(pg_session_factory: Factory) -> None:
    org, (emp, m1, m2), casual = await setup_org(pg_session_factory, "Emp", "M1", "M2")
    await report_to(pg_session_factory, org, emp, m1, m2)
    request_id = await _pending(pg_session_factory, org, emp, casual)
    results = await asyncio.gather(
        _decide(pg_session_factory, org, m1, request_id, "Release week"),
        _decide(pg_session_factory, org, m2, request_id, "Audit week"),
    )
    assert sorted(results) == [200, 409]
    winner, note = (m1, "Release week") if results[0] == 200 else (m2, "Audit week")
    request = await stored(pg_session_factory, request_id)
    assert (request.status, request.decided_by, request.decision_note) == (
        LeaveStatus.REJECTED,
        winner,
        note,
    )
    assert await days_left(pg_session_factory, org, emp, 2030) == (Decimal(5), Decimal(0))


async def test_approval_racing_the_requesters_cancel_ends_cancelled(
    pg_session_factory: Factory,
) -> None:
    """Approve-then-cancel and cancel-then-approve both leave it cancelled, days returned."""
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    request_id = await _pending(pg_session_factory, org, emp, casual)
    approved, cancelled = await asyncio.gather(
        _decide(pg_session_factory, org, mgr, request_id, None),
        _cancel(pg_session_factory, org, emp, request_id),
    )
    assert cancelled == 200 and approved in (200, 409)
    assert (await stored(pg_session_factory, request_id)).status == LeaveStatus.CANCELLED
    assert await days_left(pg_session_factory, org, emp, 2030) == (Decimal(5), Decimal(0))


async def test_a_decided_request_cannot_be_decided_again_either_way(
    pg_session_factory: Factory,
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    request_id = await _pending(pg_session_factory, org, emp, casual)
    assert await _decide(pg_session_factory, org, mgr, request_id, "No cover") == 200
    # Neither a late approval nor a second rejection overwrites the first.
    assert await _decide(pg_session_factory, org, mgr, request_id, None) == 409
    assert await _decide(pg_session_factory, org, mgr, request_id, "Changed mind") == 409
    request = await stored(pg_session_factory, request_id)
    assert (request.status, request.decision_note) == (LeaveStatus.REJECTED, "No cover")
    # Nor can the requester cancel what was already rejected.
    assert await _cancel(pg_session_factory, org, emp, request_id) == 409
