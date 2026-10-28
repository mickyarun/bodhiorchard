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

"""Carry unused leave into the new leave year, once per person, type and year.

Runs for each policy whose leave year began in the last week (in the
policy's timezone). Each person carries onto the types of the policy
they're on now, from what was unused on that same type last year; a type
switched off, or added this leave year, carries nothing. The carry is a
pair of noted ledger rows (out of the old year, into the new one), so it
shows in the person's ledger and HR can take it back with an adjustment.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeStatus
from app.models.leave_ledger import LeaveLedgerEntry, LedgerEntryType
from app.models.leave_policy import LeavePolicy
from app.repositories.leave_ledger import LeaveLedgerRepository
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.schemas.leave_report_filters import PeopleFilters
from app.services.leave.calendar_math import LeaveYearBounds, leave_year_by_label
from app.services.leave.carry_rule import added_in, carry_days, carry_notes, due_year
from app.services.leave.loss_of_pay import rebalance
from app.services.leave.policies import MemberPolicy, today_for
from app.services.leave.reports.balance_lines import balance_lines
from app.services.leave.reports.population import Person, people
from app.services.quiz_schedule_math import resolve_zone

Today = Callable[[LeavePolicy], date]


@dataclass(frozen=True)
class Carry:
    """Days one person carries on one type, from ``old_year`` into ``new_year``."""

    member: MemberPolicy
    user_id: uuid.UUID
    leave_type_id: uuid.UUID
    allocated: Decimal | None
    days: Decimal
    old_year: LeaveYearBounds
    new_year: LeaveYearBounds


async def carry_forward_org(db: AsyncSession, org_id: uuid.UUID, today: Today = today_for) -> int:
    """Carry for every policy in ``org_id`` that's due; returns the carries written.

    Works out who is owed a carry, then takes those members' locks and works
    it out again, so a second run (another worker, the next tick) waits and
    finds the carries already there. Once everyone is done nobody is locked.
    """
    due = await _due(db, org_id, today)
    if not due:
        return 0
    persons = [p for p in await people(db, org_id, None, PeopleFilters()) if _carries(p, due)]
    owed = {c.user_id for c in await _owed(db, org_id, persons, due)}
    if not owed:
        return 0
    await LeaveRequestRepository(db, org_id=org_id).lock_members(owed)
    carries = await _owed(db, org_id, [p for p in persons if p.user_id in owed], due)
    for carry in carries:
        await _write(db, carry)
    return len(carries)


async def _due(
    db: AsyncSession, org_id: uuid.UUID, today: Today
) -> dict[uuid.UUID, LeaveYearBounds]:
    """``{policy: leave year to carry into}`` for policies whose year began this week."""
    types = await LeaveTypeRepository(db, org_id=org_id).with_carry_forward()
    policies = await LeavePolicyRepository(db, org_id=org_id).by_ids({t.policy_id for t in types})
    due: dict[uuid.UUID, LeaveYearBounds] = {}
    for policy_id, policy in policies.items():
        if (year := due_year(today(policy), policy.year_start_month)) is not None:
            due[policy_id] = year
    return due


def _carries(person: Person, due: dict[uuid.UUID, LeaveYearBounds]) -> bool:
    """On a due policy and still here (not deactivated, not exited)."""
    exited = person.profile is not None and person.profile.status == EmployeeStatus.EXITED
    return (
        person.policy is not None
        and person.policy.id in due
        and person.columns.is_active
        and not exited
    )


async def _owed(
    db: AsyncSession,
    org_id: uuid.UUID,
    persons: list[Person],
    due: dict[uuid.UUID, LeaveYearBounds],
) -> list[Carry]:
    """Carries not yet written for ``persons``, from last year's balances."""
    old = await balance_lines(
        db,
        org_id,
        persons,
        lambda policy: leave_year_by_label(due[policy.id].label - 1, policy.year_start_month),
    )
    type_ids = {line.leave_type.id for balances in old.values() for line in balances.lines}
    done = await LeaveLedgerRepository(db, org_id=org_id).carried(
        {p.user_id for p in persons}, type_ids, {y.label for y in due.values()}
    )
    owed: list[Carry] = []
    for person in persons:
        balances = old.get(person.user_id)
        if balances is None or person.policy is None:
            continue
        new_year, zone = due[person.policy.id], resolve_zone(person.policy.timezone)
        for line in balances.lines:
            leave_type = line.leave_type
            days = carry_days(line)
            if (
                not days
                or (person.user_id, leave_type.id, new_year.label) in done
                or added_in(leave_type.created_at, zone, new_year)
            ):
                continue
            member = MemberPolicy(person.policy, person.profile)
            owed.append(
                Carry(member, person.user_id, leave_type.id, line.allocated, days,
                      balances.year, new_year)
            )  # fmt: skip
    return owed


async def _write(db: AsyncSession, carry: Carry) -> None:
    """Move the days: out of the old year, into the new one.

    The old year's allocation is frozen first: the carry was worked out from
    it, so a later quota edit mustn't make the two disagree.
    """
    org_id = carry.member.policy.org_id
    ledger = LeaveLedgerRepository(db, org_id=org_id)
    if carry.allocated is not None:
        await ledger.ensure_allocation(
            carry.user_id, carry.leave_type_id, carry.old_year.label, carry.allocated
        )
    out_note, in_note = carry_notes(carry.old_year, carry.new_year)
    for year, days, note in (
        (carry.old_year, -carry.days, out_note),
        (carry.new_year, carry.days, in_note),
    ):
        await ledger.create(
            LeaveLedgerEntry(
                org_id=org_id,
                user_id=carry.user_id,
                leave_type_id=carry.leave_type_id,
                leave_year=year.label,
                entry_type=LedgerEntryType.CARRY_FORWARD,
                days=days,
                note=note,
            )
        )
    # Leave already booked in the new year as loss of pay is re-priced
    # against the carried days, as after any added days.
    await rebalance(db, carry.member, carry.user_id, carry.leave_type_id, carry.new_year.start)
