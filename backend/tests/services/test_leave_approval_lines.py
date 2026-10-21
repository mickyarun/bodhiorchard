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

"""Lines under a Slack approval prompt, and where they sit in the message."""

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.schemas.leave_views import LastLeave
from app.services.leave.approval_lines import (
    balances_line,
    last_leave_line,
    recent_wfh_line,
    wfh_usage_line,
)
from app.services.leave.slack_blocks import approval_blocks


def _wfh(day: int, month: int = 10) -> SimpleNamespace:
    return SimpleNamespace(start_date=date(2026, month, day), end_date=date(2026, month, day))


def test_wfh_usage_counts_month_and_year() -> None:
    line = wfh_usage_line(date(2026, 10, 20), Decimal("4"), Decimal("22.5"))
    assert line == "With this, 4 WFH days in Oct and 22.5 this leave year."
    assert wfh_usage_line(date(2026, 10, 20), Decimal("1"), Decimal("1")).startswith(
        "With this, 1 WFH day in Oct"
    )


def test_recent_wfh_lists_newest_first_as_given() -> None:
    recent = [_wfh(13), _wfh(9), _wfh(30, month=9)]
    line = recent_wfh_line(recent)  # type: ignore[arg-type]
    assert line == "Last WFH: Tue 13 Oct · Fri 9 Oct · Wed 30 Sep"
    assert recent_wfh_line([]) is None


def test_last_leave_shows_dates_never_the_type() -> None:
    last = LastLeave(
        leave_type="Sick",
        start_date=date(2026, 10, 5),
        end_date=date(2026, 10, 6),
        days=Decimal(2),
    )
    line = last_leave_line(last)
    assert line == "Last leave: Mon 5 – Tue 6 Oct (2 days)"
    assert "Sick" not in (line or "")
    assert last_leave_line(None) is None


def _balance(name: str, allocated: str | None, available: str | None, used: str = "0") -> object:
    return SimpleNamespace(
        leave_type=SimpleNamespace(name=name),
        allocated=Decimal(allocated) if allocated is not None else None,
        available=Decimal(available) if available is not None else None,
        used=Decimal(used),
        pending=Decimal("2"),
    )


def test_balances_show_what_is_left_or_taken_never_pending() -> None:
    line = balances_line(
        [
            _balance("Casual", "12", "4"),  # type: ignore[list-item]
            _balance("Earned", "15", "10.50"),  # type: ignore[list-item]
            _balance("Unpaid", None, None, used="3"),  # type: ignore[list-item]
        ]
    )
    assert line == "Balances: Casual 4 of 12 left · Earned 10.5 of 15 left · Unpaid 3 taken"
    assert "pending" not in (line or "")


def test_an_overdrawn_balance_says_so_instead_of_a_negative_number() -> None:
    line = balances_line([_balance("Casual", "12", "-1.5")])  # type: ignore[list-item]
    assert line == "Balances: Casual overdrawn by 1.5"


def test_unused_types_without_allocation_are_skipped() -> None:
    line = balances_line(
        [
            _balance("Casual", "12", "12"),  # type: ignore[list-item]
            _balance("Sick", None, None),  # type: ignore[list-item]
            _balance("Comp off", "0", "0"),  # type: ignore[list-item]
        ]
    )
    assert line == "Balances: Casual 12 of 12 left"


def test_no_balances_means_no_line() -> None:
    assert balances_line([]) is None


def test_context_sits_between_text_and_buttons_and_is_escaped() -> None:
    blocks = approval_blocks(
        "Ravi requested leave", uuid.uuid4(), "https://app", ["<!here> 4 days"]
    )
    assert [b["type"] for b in blocks] == ["section", "context", "actions"]
    assert blocks[1]["elements"][0]["text"] == "&lt;!here&gt; 4 days"


def test_no_context_block_without_lines() -> None:
    blocks = approval_blocks("Ravi requested leave", uuid.uuid4(), "https://app")
    assert [b["type"] for b in blocks] == ["section", "actions"]
