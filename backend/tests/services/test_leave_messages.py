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
from app.services.leave.messages import (
    compose_decision_message,
    compose_request_message,
    format_range,
)


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


def test_decision_message() -> None:
    text = compose_decision_message(_request(status=LeaveStatus.REJECTED), "Priya")  # type: ignore[arg-type]
    assert text == "Your request for leave Mon 19 – Wed 21 Oct was rejected by Priya."
