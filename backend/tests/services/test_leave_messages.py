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

"""Leave notification text never reveals the leave type or reason."""

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.models.leave_request import LeaveKind, LeaveStatus
from app.schemas.leave import HighLeave
from app.services.leave.messages import (
    compose_change_message,
    compose_decision_message,
    compose_request_message,
    format_range,
)
from app.services.leave.notify import after_cancel


def _request(**overrides: object) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "kind": LeaveKind.LEAVE,
        "start_date": date(2026, 10, 19),
        "end_date": date(2026, 10, 21),
        "days": Decimal("3"),
        "status": LeaveStatus.PENDING,
        "reason": "Fever",
    }
    return SimpleNamespace(**{**base, **overrides})


def test_format_range() -> None:
    assert format_range(date(2026, 10, 19), date(2026, 10, 19)) == "Mon 19 Oct"
    assert format_range(date(2026, 10, 19), date(2026, 10, 21)) == "Mon 19 – Wed 21 Oct"
    assert format_range(date(2026, 10, 30), date(2026, 11, 2)) == "Fri 30 Oct – Mon 2 Nov"


def test_request_message_has_no_type_or_reason() -> None:
    text = compose_request_message("Ravi", _request(), auto_approved=False)  # type: ignore[arg-type]
    assert text == "Ravi requested leave Mon 19 – Wed 21 Oct (3 days)."
    assert "Fever" not in text and "sick" not in text.lower()


def test_auto_approved_wfh_reads_as_fyi() -> None:
    text = compose_request_message(
        "Ravi",
        _request(kind=LeaveKind.WFH, end_date=date(2026, 10, 19), days=Decimal("0.5")),  # type: ignore[arg-type]
        auto_approved=True,
    )
    assert (
        text == "Ravi is working from home Mon 19 Oct (0.5 days). It was approved automatically."
    )


def test_auto_approved_leave_never_names_the_type() -> None:
    one_day = _request(end_date=date(2026, 10, 19), days=Decimal("1"))
    text = compose_request_message("Asha", one_day, auto_approved=True)  # type: ignore[arg-type]
    assert text == "Asha is on leave Mon 19 Oct (1 day)."


def test_auto_approved_heads_up_keeps_the_high_leave_line() -> None:
    high = HighLeave(level="notice", taken=Decimal("16"), notice_days=15, warning_days=18)
    one_day = _request(end_date=date(2026, 10, 19), days=Decimal("1"))
    text = compose_request_message("Asha", one_day, auto_approved=True, high_leave=high)  # type: ignore[arg-type]
    assert text.endswith("(heads-up at 15).")


def test_decision_message() -> None:
    text = compose_decision_message(_request(status=LeaveStatus.REJECTED), "Priya")  # type: ignore[arg-type]
    assert text == "Your request for leave Mon 19 – Wed 21 Oct was rejected by Priya."


def test_decisions_only_resync_requests_that_were_approved() -> None:
    pending_cancelled = _request(status=LeaveStatus.CANCELLED, decided_at=None)
    approved_cancelled = _request(status=LeaveStatus.CANCELLED, decided_at=date(2026, 10, 1))
    org = uuid.uuid4()
    assert after_cancel(org, pending_cancelled).sync_request_id is None  # type: ignore[arg-type]
    assert after_cancel(org, approved_cancelled).sync_request_id is not None  # type: ignore[arg-type]


def test_change_messages_say_what_happened_never_the_type_or_reason() -> None:
    moved = _request(status=LeaveStatus.APPROVED, decision_note="Swap with Ravi")
    text = compose_change_message(moved, "Priya", withdrawn=False)  # type: ignore[arg-type]
    assert text == "Priya changed your leave to Mon 19 – Wed 21 Oct (3 days). Note: Swap with Ravi"
    assert "Fever" not in text

    gone = _request(status=LeaveStatus.REJECTED, decision_note=None)
    assert compose_change_message(gone, "Priya", withdrawn=True) == (  # type: ignore[arg-type]
        "Priya withdrew the approval for your leave Mon 19 – Wed 21 Oct (3 days)."
    )
    cut = _request(status=LeaveStatus.APPROVED, decision_note=None, days=Decimal("1"))
    assert compose_change_message(cut, "Priya", withdrawn=True).startswith(  # type: ignore[arg-type]
        "Priya ended your leave early: it now runs"
    )
