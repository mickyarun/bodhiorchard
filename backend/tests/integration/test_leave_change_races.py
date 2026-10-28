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

"""A manager changing approved leave while the requester cancels it.

Each caller has its own session. Whichever order the member lock lets
them through in, the leave ends in one state and its days come back.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._leave_errors import status_for
from app.models.leave_request import HalfDay, LeaveStatus
from app.services.leave.cancellation import cancel
from app.services.leave.changes import withdraw
from app.services.leave.errors import LeaveError
from app.services.leave.lifecycle import decide, submit
from app.services.leave.reschedule import reschedule
from tests.integration.leave_edge_support import days_left, freeze_today, stored
from tests.integration.leave_support import NOBODY, Factory, leave_body, report_to, setup_org

pytestmark = pytest.mark.integration
D = Decimal
TODAY = date(2030, 6, 3)  # a Monday
MON, TUE = date(2030, 6, 10), date(2030, 6, 11)


@pytest.fixture(autouse=True)
def _frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_today(monkeypatch, TODAY)


async def _approved(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """``(org, emp, mgr, request)``: two approved days of a 5-day type."""
    org, (emp, mgr), casual = await setup_org(factory, "Emp", "Mgr")
    await report_to(factory, org, emp, mgr)
    async with factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, MON, TUE))
        await decide(
            db, org_id=org, actor=mgr, perms=NOBODY, request_id=request.id, approve=True, note=None
        )
        await db.commit()
        return org, emp, mgr, request.id


async def _run(factory: Factory, act: Callable[[AsyncSession], Awaitable[object]]) -> int:
    async with factory() as db:
        try:
            await act(db)
            await db.commit()
            return 200
        except LeaveError as exc:
            await db.rollback()
            return status_for(exc)


async def test_a_withdrawal_racing_a_cancel_ends_one_way(pg_session_factory: Factory) -> None:
    org, emp, mgr, request_id = await _approved(pg_session_factory)
    withdrawn, cancelled = await asyncio.gather(
        _run(
            pg_session_factory,
            lambda db: withdraw(
                db, org_id=org, actor=mgr, perms=NOBODY, request_id=request_id, note="Release"
            ),
        ),
        _run(pg_session_factory, lambda db: cancel(db, org, emp, request_id)),
    )
    # Whichever went second found the leave no longer approved.
    assert sorted((withdrawn, cancelled)) == [200, 409]
    expected = LeaveStatus.REJECTED if withdrawn == 200 else LeaveStatus.CANCELLED
    assert (await stored(pg_session_factory, request_id)).status == expected
    assert await days_left(pg_session_factory, org, emp, 2030) == (D(5), D(0))


async def test_a_move_racing_a_cancel_never_revives_the_leave(pg_session_factory: Factory) -> None:
    org, emp, mgr, request_id = await _approved(pg_session_factory)
    moved, cancelled = await asyncio.gather(
        _run(
            pg_session_factory,
            lambda db: reschedule(
                db,
                org_id=org,
                actor=mgr,
                perms=NOBODY,
                request_id=request_id,
                start=date(2030, 6, 12),
                end=date(2030, 6, 14),
                half_day=HalfDay.NONE,
                note="Moved",
            ),
        ),
        _run(pg_session_factory, lambda db: cancel(db, org, emp, request_id)),
    )
    # Moved then cancelled, or cancelled then the move refused: cancelled either way.
    assert cancelled == 200 and moved in (200, 409)
    assert (await stored(pg_session_factory, request_id)).status == LeaveStatus.CANCELLED
    assert await days_left(pg_session_factory, org, emp, 2030) == (D(5), D(0))
