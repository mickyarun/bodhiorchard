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

"""Does a work-from-home request need a manager's approval? (pure)

Under ``auto_within_allowance``, a request is approved automatically when,
for every calendar month it touches, the employee's approved and pending
WFH days plus the new ones stay within the policy's monthly allowance.
Otherwise the whole request goes to the managers — a request is never
half-approved.
"""

from collections.abc import Mapping
from decimal import Decimal

from app.models.leave_policy import WfhApproval

Month = tuple[int, int]


def needs_approval(
    mode: WfhApproval,
    allowance: int,
    *,
    already: Mapping[Month, Decimal],
    requested: Mapping[Month, Decimal],
) -> bool:
    """True if a manager has to approve this WFH request."""
    if mode == WfhApproval.AUTO:
        return False
    if mode == WfhApproval.REQUIRED:
        return True
    limit = Decimal(allowance)
    return any(
        already.get(month, Decimal("0")) + days > limit for month, days in requested.items()
    )


def auto_days_left(mode: WfhApproval, allowance: int, used_this_month: Decimal) -> int | None:
    """Whole WFH days still auto-approved this month; None if not applicable."""
    if mode != WfhApproval.AUTO_WITHIN_ALLOWANCE:
        return None
    return max(0, int(Decimal(allowance) - used_this_month))
