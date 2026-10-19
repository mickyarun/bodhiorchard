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

"""A member's balances and ledger; HR adjustments and recalculation."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._leave_admin import CONFIGURE
from app.core.deps import (
    PermissionSet,
    get_current_user,
    get_db,
    get_permission_set,
    require_permissions,
)
from app.models.user import User
from app.schemas.leave_config import Recalculate, RecalculateResult
from app.schemas.leave_policy import BalanceAdjust, MemberBalances
from app.services.leave import adjustments
from app.services.leave.member_balances import (
    may_view_balances,
    member_balances,
    require_member,
)

router = APIRouter(tags=["leave"])


@router.get("/balances/{user_id}", response_model=MemberBalances)
async def get_member_balances(
    user_id: uuid.UUID,
    year: int | None = Query(None, ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> MemberBalances:
    """Balances and ledger: for the member, their managers, and HR."""
    await _require_balance_access(db, current_user, perms, user_id)
    return await member_balances(db, current_user.org_id, user_id, year)


async def _require_balance_access(
    db: AsyncSession, current_user: User, perms: PermissionSet, user_id: uuid.UUID
) -> None:
    """404 for strangers, 403 unless the caller may see this person's balances.

    Changing a balance returns it, so the write routes check this too:
    leave:configure alone doesn't show who used which leave.
    """
    await require_member(db, current_user.org_id, user_id)
    if not await may_view_balances(db, current_user, perms, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You can't see this person's balances."
        )


def _change(
    current_user: User,
    perms: PermissionSet,
    user_id: uuid.UUID,
    type_id: uuid.UUID,
    year: int | None,
) -> adjustments.BalanceChange:
    return adjustments.BalanceChange(
        org_id=current_user.org_id,
        actor_id=current_user.id,
        actor_is_owner=perms.is_owner,
        user_id=user_id,
        leave_type_id=type_id,
        leave_year=year,
    )


@router.post("/balances/{user_id}/adjust", response_model=MemberBalances)
async def adjust_balance(
    user_id: uuid.UUID,
    body: BalanceAdjust,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> MemberBalances:
    """Add or remove days, with a note (HR; not on your own balance)."""
    await _require_balance_access(db, current_user, perms, user_id)
    change = _change(current_user, perms, user_id, body.leave_type_id, body.leave_year)
    label = await adjustments.adjust(db, change, body.days, body.note)
    return await member_balances(db, current_user.org_id, user_id, label)


@router.post("/balances/{user_id}/recalculate", response_model=RecalculateResult)
async def recalculate_allocation(
    user_id: uuid.UUID,
    body: Recalculate,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> RecalculateResult:
    """Re-run a frozen year's allocation and book any difference (HR)."""
    await _require_balance_access(db, current_user, perms, user_id)
    change = _change(current_user, perms, user_id, body.leave_type_id, body.leave_year)
    result = await adjustments.recalculate(db, change)
    return RecalculateResult(
        frozen=result.frozen,
        recalculated=result.recalculated,
        correction=result.correction,
        balances=await member_balances(db, current_user.org_id, user_id, result.leave_year),
    )
