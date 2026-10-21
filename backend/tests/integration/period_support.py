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

"""Period leave set-up shared by the period-leave integration tests."""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.models.employee_profile import Gender
from app.models.leave_type import LeaveType
from app.repositories.employee_profile import EmployeeProfileRepository
from app.services.leave.policies import ensure_default_policy
from tests.integration.leave_support import Factory


async def add_period_leave(
    factory: Factory, org: uuid.UUID, *women: uuid.UUID, quota: str = "12"
) -> uuid.UUID:
    """Period leave on the default policy (female only, self-approving, 1 a month).

    Each of ``women`` is recorded as female on their profile.
    """
    async with factory() as db:
        policy = await ensure_default_policy(db, org)
        period = LeaveType(
            org_id=org, policy_id=policy.id, name="Period leave", code="PERIOD",
            annual_quota_days=Decimal(quota), eligible_genders=[Gender.FEMALE],
            auto_approve=True, monthly_limit_days=Decimal("1"), counts_toward_warning=False,
        )  # fmt: skip
        db.add(period)
        profiles = EmployeeProfileRepository(db, org_id=org)
        for woman in women:
            profile = await profiles.get_by_user(woman)
            assert profile is not None
            profile.gender = Gender.FEMALE
        await db.commit()
        return period.id
