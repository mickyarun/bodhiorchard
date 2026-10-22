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

"""Shared lookups for the leave configuration routes."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_policy import LeavePolicy
from app.models.leave_type import LeaveType
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_policy_members import LeavePolicyMemberRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.schemas.leave_policy import PolicyRead
from app.schemas.leave_type import LeaveTypeRead
from app.services.leave.errors import LeaveNotFoundError


async def load_policy(db: AsyncSession, org_id: uuid.UUID, policy_id: uuid.UUID) -> LeavePolicy:
    """A policy in this org, or 404."""
    policy = await LeavePolicyRepository(db, org_id=org_id).get_by_id(policy_id)
    if policy is None:
        raise LeaveNotFoundError("Policy not found.")
    return policy


async def load_type(db: AsyncSession, org_id: uuid.UUID, type_id: uuid.UUID) -> LeaveType:
    """A leave type in this org, or 404."""
    leave_type = await LeaveTypeRepository(db, org_id=org_id).get_by_id(type_id)
    if leave_type is None:
        raise LeaveNotFoundError("Leave type not found.")
    return leave_type


async def policy_read(db: AsyncSession, policy: LeavePolicy) -> PolicyRead:
    """Wire shape of a policy with its usage counts."""
    repo = LeavePolicyRepository(db, org_id=policy.org_id)
    return PolicyRead(
        id=policy.id,
        name=policy.name,
        country_code=policy.country_code,
        subdivision_code=policy.subdivision_code,
        timezone=policy.timezone,
        working_days=list(policy.working_days),
        year_start_month=policy.year_start_month,
        wfh_approval=policy.wfh_approval,
        wfh_monthly_auto_days=policy.wfh_monthly_auto_days,
        backdate_limit_days=policy.backdate_limit_days,
        optional_holiday_quota=policy.optional_holiday_quota,
        leave_notice_days=policy.leave_notice_days,
        leave_warning_days=policy.leave_warning_days,
        proration_method=policy.proration_method,
        proration_cutoff_day=policy.proration_cutoff_day,
        allocation_rounding=policy.allocation_rounding,
        is_default=policy.is_default,
        employee_count=await LeavePolicyMemberRepository(db, org_id=policy.org_id).count_employees(
            policy
        ),
        has_requests=await repo.has_requests(policy.id),
    )


def type_read(t: LeaveType) -> LeaveTypeRead:
    """Wire shape of a policy's leave type."""
    return LeaveTypeRead(
        id=t.id,
        policy_id=t.policy_id,
        template_id=t.template_id,
        own_quota=t.own_quota,
        name=t.name,
        code=t.code,
        annual_quota_days=t.annual_quota_days,
        accrual=t.accrual,
        is_paid=t.is_paid,
        is_encashable=t.is_encashable,
        counts_toward_warning=t.counts_toward_warning,
        eligible_genders=t.eligible_genders,
        auto_approve=t.auto_approve,
        monthly_limit_days=t.monthly_limit_days,
        stops_at_balance=t.stops_at_balance,
        color_key=t.color_key,
        is_active=t.is_active,
    )
