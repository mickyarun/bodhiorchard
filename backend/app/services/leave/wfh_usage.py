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

"""How much WFH a member has used, and whether a new request is auto-approved."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_policy import LeavePolicy
from app.models.leave_request import HalfDay, LeaveKind
from app.services.leave.month_usage import booked_by_month, requested_by_month
from app.services.leave.wfh_policy import Month, needs_approval


async def wfh_days_by_month(
    db: AsyncSession, policy: LeavePolicy, user_id: uuid.UUID, start: date, end: date
) -> dict[Month, Decimal]:
    """Approved + pending WFH working days per month across the months of a range."""
    return await booked_by_month(db, policy, user_id, start, end, kind=LeaveKind.WFH)


async def wfh_auto_approved(
    db: AsyncSession,
    policy: LeavePolicy,
    user_id: uuid.UUID,
    start: date,
    end: date,
    half_day: HalfDay,
) -> bool:
    """True if the policy approves this WFH request without a manager."""
    requested = await requested_by_month(db, policy, start, end, half_day)
    already = await wfh_days_by_month(db, policy, user_id, start, end)
    return not needs_approval(
        policy.wfh_approval, policy.wfh_monthly_auto_days, already=already, requested=requested
    )
