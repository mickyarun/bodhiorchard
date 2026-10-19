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

"""A member's balances and ledger; HR adjustments."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._leave_admin import CONFIGURE
from app.core.deps import PermissionSet, get_current_user, get_db, get_permission_set
from app.models.leave_ledger import LeaveLedgerEntry, LedgerEntryType
from app.models.user import User
from app.repositories.leave_ledger import LeaveLedgerRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.user import UserRepository
from app.schemas.leave import PersonRef
from app.schemas.leave_policy import BalanceAdjust, LedgerEntryRead, MemberBalances
from app.services.leave.approvers import APPROVE, reports_of
from app.services.leave.balances import balances_for
from app.services.leave.calendar_math import leave_year_bounds, leave_year_by_label
from app.services.leave.policies import resolve_member_policy, today_for
from app.services.leave.summary import balance_schema, year_schema

router = APIRouter(tags=["leave"])


async def _may_view(
    db: AsyncSession, current_user: User, perms: PermissionSet, user_id: uuid.UUID
) -> bool:
    if user_id == current_user.id or perms.has_any((CONFIGURE, APPROVE)):
        return True
    return user_id in await reports_of(db, current_user.org_id, current_user.id)


async def _balances(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, year_label: int | None
) -> MemberBalances:
    member = await resolve_member_policy(db, org_id, user_id)
    policy = member.policy
    year = (
        leave_year_by_label(year_label, policy.year_start_month)
        if year_label
        else leave_year_bounds(today_for(policy), policy.year_start_month)
    )
    lines = await balances_for(
        db, policy=policy, profile=member.profile, user_id=user_id, year=year
    )
    entries = await LeaveLedgerRepository(db, org_id=org_id).list_for(user_id, year.label)
    names = await UserRepository(db).get_names_by_ids(
        {user_id} | {e.created_by for e in entries if e.created_by}
    )
    return MemberBalances(
        user=PersonRef(user_id=user_id, name=names.get(user_id, "Unknown")),
        policy_name=policy.name,
        leave_year=year_schema(year),
        balances=[balance_schema(line) for line in lines],
        ledger=[
            LedgerEntryRead(
                id=e.id,
                leave_type_id=e.leave_type_id,
                leave_year=e.leave_year,
                entry_type=e.entry_type.value,
                days=e.days,
                note=e.note,
                created_by=PersonRef(user_id=e.created_by, name=names.get(e.created_by, "Unknown"))
                if e.created_by
                else None,
                created_at=e.created_at.date(),
            )
            for e in entries
        ],
    )


@router.get("/balances/{user_id}", response_model=MemberBalances)
async def member_balances(
    user_id: uuid.UUID,
    year: int | None = Query(None, ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> MemberBalances:
    """Balances and ledger: for the member, their managers, and HR."""
    if not await _may_view(db, current_user, perms, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You can't see this person's balances."
        )
    return await _balances(db, current_user.org_id, user_id, year)


@router.post("/balances/{user_id}/adjust", response_model=MemberBalances)
async def adjust_balance(
    user_id: uuid.UUID,
    body: BalanceAdjust,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> MemberBalances:
    """Add or remove days, with a note (HR; not on your own balance)."""
    if not perms.has(CONFIGURE) or (user_id == current_user.id and not perms.is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ask another HR member to adjust your own balance.",
        )
    org_id = current_user.org_id
    member = await resolve_member_policy(db, org_id, user_id)
    leave_type = await LeaveTypeRepository(db, org_id=org_id).get_by_id(body.leave_type_id)
    if leave_type is None or leave_type.policy_id != member.policy.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That leave type isn't on this person's policy.",
        )
    label = (
        body.leave_year
        or leave_year_bounds(today_for(member.policy), member.policy.year_start_month).label
    )
    await LeaveLedgerRepository(db, org_id=org_id).create(
        LeaveLedgerEntry(
            org_id=org_id,
            user_id=user_id,
            leave_type_id=leave_type.id,
            leave_year=label,
            entry_type=LedgerEntryType.ADJUSTMENT,
            days=body.days,
            note=body.note.strip(),
            created_by=current_user.id,
        )
    )
    return await _balances(db, org_id, user_id, label)
