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


"""The heads-up and warning lines on leave taken, and the approver's line."""

from decimal import Decimal

from app.models.leave_policy import LeavePolicy
from app.schemas.leave import HighLeave
from app.services.leave.high_leave import assess, has_lines
from app.services.leave.messages import high_leave_line


def policy(notice: int | None, warning: int | None) -> LeavePolicy:
    return LeavePolicy(name="Tech", leave_notice_days=notice, leave_warning_days=warning)


def test_levels_step_up_at_each_line() -> None:
    tech = policy(15, 18)
    assert assess(tech, Decimal("14.5")) is None
    assert assess(tech, Decimal(15)) == HighLeave(
        level="notice", taken=Decimal(15), notice_days=15, warning_days=18
    )
    assert assess(tech, Decimal(18)).level == "warning"  # type: ignore[union-attr]


def test_a_policy_without_lines_never_warns() -> None:
    assert not has_lines(policy(None, None))
    assert assess(policy(None, None), Decimal(100)) is None
    assert assess(policy(None, 10), Decimal(12)).level == "warning"  # type: ignore[union-attr]


def test_the_approver_line_names_days_and_line_but_no_type() -> None:
    notice = HighLeave(level="notice", taken=Decimal(16), notice_days=15, warning_days=18)
    warning = HighLeave(level="warning", taken=Decimal("19.5"), notice_days=15, warning_days=18)
    assert (
        high_leave_line(notice) == "With this, they've taken 16 days this year (heads-up at 15)."
    )
    assert high_leave_line(warning) == (
        "With this, they've taken 19.5 days this year, past the 18-day line."
    )
