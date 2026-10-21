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
"""Extra lines under a Slack approval prompt (pure).

They go in a context block, never the message's fallback text, so they
don't show in lock-screen previews. Nothing here names the type of the
request being decided.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from app.models.leave_request import LeaveRequest
from app.schemas.leave_summary import Balance
from app.schemas.leave_views import LastLeave
from app.services.leave.messages import days_text, format_range, number


def format_balance(balance: Balance) -> str:
    """One leave type's figure for an approver: "Casual 4 of 12 left", "Unpaid 3 taken"
    or "Casual overdrawn by 2" (after a downward adjustment, say).

    Pending days aren't shown: a pending figure on one type would hint at
    which type this request is.
    """
    name = balance.leave_type.name
    if balance.available is None or balance.allocated is None:
        return f"{name} {number(balance.used)} taken"
    if balance.available < 0:
        return f"{name} overdrawn by {number(-balance.available)}"
    return f"{name} {number(balance.available)} of {number(balance.allocated)} left"


def _worth_showing(balance: Balance) -> bool:
    """Skip types with nothing allocated and nothing taken (pending ignored, as above)."""
    return bool(balance.allocated) or balance.used > 0


def balances_line(balances: Sequence[Balance]) -> str | None:
    """ "Balances: Casual 4 of 12 left · Unpaid 3 taken · …", or None without any."""
    parts = [format_balance(b) for b in balances if _worth_showing(b)]
    return "Balances: " + " · ".join(parts) if parts else None


def last_leave_line(last: LastLeave | None) -> str | None:
    """ "Last leave: Mon 6 – Tue 7 Oct (2 days)" — dates only, never the type."""
    if last is None:
        return None
    return f"Last leave: {format_range(last.start_date, last.end_date)} ({days_text(last.days)})"


def wfh_usage_line(month: date, month_days: Decimal, year_days: Decimal) -> str:
    """ "With this, 4 WFH days in Oct and 22 this leave year." (approved + pending)."""
    return (
        f"With this, {number(month_days)} WFH {'day' if month_days == 1 else 'days'} "
        f"in {month:%b} and {number(year_days)} this leave year."
    )


def recent_wfh_line(recent: Sequence[LeaveRequest]) -> str | None:
    """ "Last WFH: Mon 13 Oct · Thu 9 Oct · Tue 30 Sep", or None if they've had none."""
    if not recent:
        return None
    return "Last WFH: " + " · ".join(format_range(r.start_date, r.end_date) for r in recent)
