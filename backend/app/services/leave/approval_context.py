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

"""What an approver sees about each requester: balances and their last leave.

Batched for the whole page. Balances are the requester's current leave year
on their own policy, from the same builder as the reports, so a card and the
Balances report never disagree.
"""

import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_type import LeaveType
from app.repositories.leave_report import LeaveReportRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.schemas.leave_report_filters import PeopleFilters
from app.schemas.leave_summary import Balance
from app.schemas.leave_views import LastLeave
from app.services.leave.policies import today_for
from app.services.leave.reports.balance_lines import balance_lines, leave_year_for
from app.services.leave.reports.population import people
from app.services.leave.summary import balance_schema
from app.services.leave.type_privacy import shown, visible


@dataclass(frozen=True)
class RequesterContext:
    """Per-requester extras for approval cards."""

    balances: dict[uuid.UUID, list[Balance]] = field(default_factory=dict)
    years: dict[uuid.UUID, int] = field(default_factory=dict)
    last_leave: dict[uuid.UUID, LastLeave] = field(default_factory=dict)


async def requester_context(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_ids: Collection[uuid.UUID],
    today: date,
    *,
    sees_all: bool,
) -> RequesterContext:
    """Balances by type and the last leave taken, for each requester.

    ``today`` is only the fallback for someone with no policy at all.
    Gender-limited types are left out unless ``sees_all``
    (:mod:`app.services.leave.type_privacy`).
    """
    if not user_ids:
        return RequesterContext()
    persons = await people(db, org_id, frozenset(user_ids), PeopleFilters())
    balances = await balance_lines(db, org_id, persons, leave_year_for(None))
    # "Today" on each member's policy, as balances use; UTC ``today`` without one.
    cutoffs = {p.user_id: today_for(p.policy) if p.policy else today for p in persons}
    last = await LeaveReportRepository(db, org_id=org_id).last_taken(cutoffs)
    types = await LeaveTypeRepository(db, org_id=org_id).by_ids(
        {r.leave_type_id for r in last if r.leave_type_id}
    )
    return RequesterContext(
        balances={
            user: [
                balance_schema(line)
                for line in visible(mine.lines, lambda line: line.leave_type, sees_all=sees_all)
            ]
            for user, mine in balances.items()
        },
        years={user: mine.year.label for user, mine in balances.items()},
        last_leave={
            r.user_id: LastLeave(
                leave_type=_type_name(types.get(r.leave_type_id), sees_all)
                if r.leave_type_id
                else None,
                start_date=r.start_date,
                end_date=r.end_date,
                days=r.days,
            )
            for r in last
        },
    )


def _type_name(leave_type: LeaveType | None, sees_all: bool) -> str | None:
    return leave_type.name if leave_type and shown(leave_type, sees_all=sees_all) else None
