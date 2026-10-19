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

"""Which dates and request shapes are refused before any day counting."""

import uuid
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.models.leave_request import HalfDay, LeaveKind
from app.schemas.leave import LeaveRequestCreate
from app.services.leave.date_rules import date_problems

TODAY = date(2026, 10, 19)


def _codes(start: date, end: date, *, year_start_month: int = 1) -> list[str]:
    problems = date_problems(
        start, end, today=TODAY, backdate_limit_days=7, year_start_month=year_start_month
    )
    return [code for code, _ in problems]


def test_backdating_is_allowed_up_to_the_limit() -> None:
    week_ago = TODAY - timedelta(days=7)
    assert _codes(week_ago, week_ago) == []
    eight_days = TODAY - timedelta(days=8)
    assert _codes(eight_days, eight_days) == ["too_far_back"]


def test_requests_cannot_cross_a_leave_year() -> None:
    assert _codes(date(2026, 12, 31), date(2027, 1, 1)) == ["crosses_leave_year"]
    # With an April leave year, New Year is mid-year.
    assert _codes(date(2026, 12, 31), date(2027, 1, 1), year_start_month=4) == []
    assert _codes(date(2027, 3, 31), date(2027, 4, 1), year_start_month=4) == [
        "crosses_leave_year"
    ]


def test_requests_stop_at_the_end_of_next_leave_year() -> None:
    assert _codes(date(2027, 12, 31), date(2027, 12, 31)) == []
    assert _codes(date(2028, 1, 3), date(2028, 1, 3)) == ["too_far_ahead"]


def _leave(**kw: object) -> LeaveRequestCreate:
    fields: dict[str, object] = {
        "kind": LeaveKind.LEAVE,
        "leave_type_id": uuid.uuid4(),
        "start_date": TODAY,
        "end_date": TODAY,
    }
    fields.update(kw)
    return LeaveRequestCreate.model_validate(fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"end_date": TODAY - timedelta(days=1)},
        {"end_date": TODAY + timedelta(days=1), "half_day": HalfDay.FIRST_HALF},
        {"leave_type_id": None},
        {"kind": LeaveKind.OPTIONAL_HOLIDAY, "holiday_id": None},
        # Longer than any leave year: refused before a day is counted.
        {"start_date": date(1, 1, 1)},
    ],
)
def test_malformed_requests_are_refused(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _leave(**fields)


def test_fields_that_do_not_apply_are_dropped() -> None:
    wfh = _leave(kind=LeaveKind.WFH)
    assert wfh.leave_type_id is None
    holiday = _leave(
        kind=LeaveKind.OPTIONAL_HOLIDAY, holiday_id=uuid.uuid4(), half_day=HalfDay.FIRST_HALF
    )
    assert holiday.half_day == HalfDay.NONE
    assert holiday.leave_type_id is None
