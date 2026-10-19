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

"""HR changes to a member's balance: manual adjustments and recalculation.

Both write ledger rows (never rewriting a frozen allocation), take the
member's lock like submit and approve do, and are refused on your own
balance unless you're the owner.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_ledger import LeaveLedgerEntry, LedgerEntryType
from app.models.leave_type import LeaveType
from app.repositories.leave_ledger import LeaveLedgerRepository
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.services.leave.allocation import allocation_for_year
from app.services.leave.balances import proration_rule
from app.services.leave.calendar_math import (
    LeaveYearBounds,
    leave_year_bounds,
    leave_year_by_label,
)
from app.services.leave.errors import (
    LeaveConflictError,
    LeaveForbiddenError,
    LeaveInvalidError,
)
from app.services.leave.member_balances import require_member
from app.services.leave.policies import (
    MemberPolicy,
    effective_from,
    resolve_member_policy,
    today_for,
)


@dataclass(frozen=True)
class BalanceChange:
    """Who is changing whose balance, for which type and leave year."""

    org_id: uuid.UUID
    actor_id: uuid.UUID
    actor_is_owner: bool
    user_id: uuid.UUID
    leave_type_id: uuid.UUID
    leave_year: int | None


@dataclass(frozen=True)
class Recalculation:
    """The frozen allocation, what the rules give now, and the correction."""

    leave_year: int
    frozen: Decimal
    recalculated: Decimal
    correction: Decimal


async def adjust(db: AsyncSession, change: BalanceChange, days: Decimal, note: str) -> int:
    """Add or remove days with a note; returns the leave year it applies to."""
    member, leave_type, year = await _prepare(db, change)
    await LeaveLedgerRepository(db, org_id=change.org_id).create(
        LeaveLedgerEntry(
            org_id=change.org_id,
            user_id=change.user_id,
            leave_type_id=leave_type.id,
            leave_year=year.label,
            entry_type=LedgerEntryType.ADJUSTMENT,
            days=days,
            note=note.strip(),
            created_by=change.actor_id,
        )
    )
    return year.label


async def recalculate(db: AsyncSession, change: BalanceChange) -> Recalculation:
    """Re-run the allocation rule for a frozen year and book the difference.

    Use it after fixing a joining date or a policy's proration rule: the
    year's allocation was fixed on first use, so it doesn't follow those
    edits by itself. The gap is written as a correction, so the original
    allocation and every earlier fix stay visible in the ledger.
    """
    member, leave_type, year = await _prepare(db, change)
    if leave_type.annual_quota_days is None:
        raise LeaveInvalidError(
            f"{leave_type.name} has no limit, so there's nothing to recalculate."
        )
    ledger = LeaveLedgerRepository(db, org_id=change.org_id)
    allocation, corrections = await ledger.frozen_allocation(
        change.user_id, leave_type.id, year.label
    )
    if allocation is None:
        raise LeaveConflictError(
            "This year's allocation isn't fixed yet, so it already follows the current rules."
        )
    frozen = allocation + corrections
    recalculated = allocation_for_year(
        leave_type.annual_quota_days,
        effective_from(member.profile),
        year.start,
        year.end,
        proration_rule(member.policy),
    )
    correction = recalculated - frozen
    if correction:
        await ledger.create(
            LeaveLedgerEntry(
                org_id=change.org_id,
                user_id=change.user_id,
                leave_type_id=leave_type.id,
                leave_year=year.label,
                entry_type=LedgerEntryType.CORRECTION,
                days=correction,
                note=f"Recalculated allocation: {frozen} → {recalculated} days",
                created_by=change.actor_id,
            )
        )
    return Recalculation(year.label, frozen, recalculated, correction)


async def _prepare(
    db: AsyncSession, change: BalanceChange
) -> tuple[MemberPolicy, LeaveType, LeaveYearBounds]:
    """Check who may change what, lock the member, and resolve type and year."""
    if change.user_id == change.actor_id and not change.actor_is_owner:
        raise LeaveForbiddenError("Ask another HR member to change your own balance.")
    await require_member(db, change.org_id, change.user_id)
    await LeaveRequestRepository(db, org_id=change.org_id).lock_member(change.user_id)
    member = await resolve_member_policy(db, change.org_id, change.user_id)
    policy = member.policy
    leave_type = await LeaveTypeRepository(db, org_id=change.org_id).get_by_id(
        change.leave_type_id
    )
    if leave_type is None or leave_type.policy_id != policy.id:
        raise LeaveInvalidError("That leave type isn't on this person's policy.")
    year = (
        leave_year_by_label(change.leave_year, policy.year_start_month)
        if change.leave_year
        else leave_year_bounds(today_for(policy), policy.year_start_month)
    )
    return member, leave_type, year
