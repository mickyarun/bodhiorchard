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

"""A member's balances and ledger as HR, their managers and they see them."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet
from app.models.user import User
from app.repositories.leave_ledger import LeaveLedgerRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.user import UserRepository
from app.schemas.leave import PersonRef
from app.schemas.leave_policy import LedgerEntryRead, MemberBalances
from app.services.leave.balances import balances_for, day_in_year
from app.services.leave.calendar_math import leave_year_bounds, leave_year_by_label
from app.services.leave.errors import LeaveNotFoundError
from app.services.leave.policies import resolve_member_policy, today_for
from app.services.leave.report_scope import may_view_member_leave
from app.services.leave.summary import balance_schema, year_schema
from app.services.leave.type_privacy import is_restricted, visible


async def require_member(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Refuse anyone who isn't a member of this org (never touch other orgs)."""
    if not await UserRepository(db).is_member_of_org(user_id, org_id):
        raise LeaveNotFoundError("Member not found.")


async def may_view_balances(
    db: AsyncSession, viewer: User, perms: PermissionSet, user_id: uuid.UUID
) -> bool:
    """Self, their managers, HR (leave:approve) and leave:reports.

    Not leave:configure on its own: per-type used/pending days next to the
    calendar's "on leave" would tell a policy admin who is off sick.
    """
    return await may_view_member_leave(db, viewer, perms, user_id)


async def member_balances(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    year_label: int | None,
    *,
    sees_restricted: bool,
) -> MemberBalances:
    """A member's balances and ledger for one leave year (the current one by default).

    Gender-limited types, and their ledger rows, are left out unless
    ``sees_restricted`` (:mod:`app.services.leave.type_privacy`).
    """
    member = await resolve_member_policy(db, org_id, user_id)
    policy = member.policy
    today = today_for(policy)
    year = (
        leave_year_by_label(year_label, policy.year_start_month)
        if year_label
        else leave_year_bounds(today, policy.year_start_month)
    )
    lines = await balances_for(
        db,
        policy=policy,
        profile=member.profile,
        user_id=user_id,
        year=year,
        on=day_in_year(today, year),
    )
    if not sees_restricted:
        lines = [line for line in lines if not is_restricted(line.leave_type)]
    entries = await LeaveLedgerRepository(db, org_id=org_id).list_for(user_id, year.label)
    if not sees_restricted:
        types = await LeaveTypeRepository(db, org_id=org_id).by_ids(
            {e.leave_type_id for e in entries}
        )
        entries = visible(entries, lambda e: types.get(e.leave_type_id), sees_all=False)
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
