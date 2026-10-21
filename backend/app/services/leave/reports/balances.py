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

"""Balances for everyone in scope for one leave year.

Each member's year is their own policy's leave year with the requested
label (the current one by default). Lines come from :func:`balance_lines`,
the same builder the summary and approvals use.
"""

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.leave_report_filters import BalanceFilters
from app.schemas.leave_reports import BalanceReport, BalanceRow
from app.services.leave.balances import BalanceLine
from app.services.leave.report_scope import ReportScope
from app.services.leave.reports.balance_lines import balance_lines, leave_year_for
from app.services.leave.reports.population import people, scoped_ids


def encashable(line: BalanceLine) -> Decimal | None:
    """Unused days paid out at exit for an encashable type, else None."""
    if not line.leave_type.is_encashable or line.available is None:
        return None
    return max(line.available, Decimal(0))


async def balance_report(
    db: AsyncSession, org_id: uuid.UUID, scope: ReportScope, f: BalanceFilters
) -> BalanceReport:
    """One row per member per active leave type on their policy."""
    ids = await scoped_ids(db, org_id, scope, f)
    persons = await people(db, org_id, ids, f)
    balances = await balance_lines(db, org_id, persons, leave_year_for(f.year))
    rows = []
    for p in persons:
        mine = balances.get(p.user_id)
        if mine is None:
            continue
        for line in mine.lines:
            rows.append(
                BalanceRow(
                    **p.columns.model_dump(),
                    leave_year=mine.year.label,
                    leave_type_id=line.leave_type.id,
                    leave_type=line.leave_type.name,
                    allocated=line.allocated,
                    adjustments=line.adjustments,
                    used=line.used,
                    pending=line.pending,
                    available=line.available,
                    encashable=encashable(line),
                    lop_days=mine.lop_days,
                )
            )
    return BalanceReport(rows=rows)
