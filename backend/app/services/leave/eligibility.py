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

"""Who on a policy can see and request a leave type (pure).

A type for women only (period leave) is hidden from everyone else: it's
not on their balance cards or in their request dialog, and a request for
it is refused. Someone with no gender on their profile can't use it until
HR fills it in.
"""

from collections.abc import Iterable

from app.models.employee_profile import EmployeeProfile, Gender
from app.models.leave_type import LeaveEligibility, LeaveType


def can_use(leave_type: LeaveType, profile: EmployeeProfile | None) -> bool:
    """True if this person may see and request ``leave_type``."""
    if leave_type.eligibility == LeaveEligibility.EVERYONE:
        return True
    return profile is not None and profile.gender == Gender.FEMALE


def usable_types(types: Iterable[LeaveType], profile: EmployeeProfile | None) -> list[LeaveType]:
    """The types in ``types`` this person may use, in the same order."""
    return [t for t in types if can_use(t, profile)]
