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

"""Setup shared by the carry-forward tests: a clock, type edits and ledger reads."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.models.leave_ledger import LeaveLedgerEntry, LedgerEntryType
from app.models.leave_policy import LeavePolicy
from app.models.leave_type import LeaveType
from app.services.leave.carry_forward import Today, carry_forward_org
from tests.integration.leave_support import Factory

D = Decimal
# This year into the next: the types the tests set up existed all of the old year.
OLD = date.today().year
NEW = OLD + 1


def on(day: date) -> Today:
    """A clock that says ``day`` for every policy."""
    return lambda _policy: day


async def set_type(factory: Factory, type_id: uuid.UUID, **fields: object) -> None:
    async with factory() as db:
        leave_type = await db.get(LeaveType, type_id)
        assert leave_type is not None
        for field, value in fields.items():
            setattr(leave_type, field, value)
        await db.commit()


async def add_type(
    factory: Factory, policy_id: uuid.UUID, code: str, **fields: object
) -> uuid.UUID:
    async with factory() as db:
        policy = await db.get(LeavePolicy, policy_id)
        assert policy is not None
        leave_type = LeaveType(org_id=policy.org_id, policy_id=policy_id, name=code, code=code)
        for field, value in fields.items():
            setattr(leave_type, field, value)
        db.add(leave_type)
        await db.commit()
        return leave_type.id


async def policy_of(factory: Factory, type_id: uuid.UUID) -> uuid.UUID:
    async with factory() as db:
        leave_type = await db.get(LeaveType, type_id)
        assert leave_type is not None
        return leave_type.policy_id


async def run(factory: Factory, org: uuid.UUID, day: date) -> int:
    async with factory() as db:
        written = await carry_forward_org(db, org, today=on(day))
        await db.commit()
        return written


async def entries(
    factory: Factory, user: uuid.UUID, kind: LedgerEntryType
) -> list[LeaveLedgerEntry]:
    async with factory() as db:
        rows = await db.execute(
            select(LeaveLedgerEntry).where(
                LeaveLedgerEntry.user_id == user, LeaveLedgerEntry.entry_type == kind
            )
        )
        return list(rows.scalars().all())


async def carried(factory: Factory, user: uuid.UUID) -> list[tuple[object, ...]]:
    """``(type, leave_year, days)`` of each carry into ``user``'s balance."""
    rows = await entries(factory, user, LedgerEntryType.CARRY_FORWARD)
    return [(e.leave_type_id, e.leave_year, e.days) for e in rows if e.days > 0]
