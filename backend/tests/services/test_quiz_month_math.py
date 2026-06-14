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

"""Unit tests for the month-key helpers used by the monthly SP rollup."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.quiz_schedule_math import (
    current_month_key,
    month_bounds,
    next_quiz_at,
    previous_month_key,
)


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 6, 1), "2026-05"),  # first of month → prior month
        (date(2026, 1, 1), "2025-12"),  # year boundary
        (date(2026, 3, 1), "2026-02"),  # leap-year February still resolves
        (date(2026, 12, 15), "2026-11"),
    ],
)
def test_previous_month_key(today: date, expected: str) -> None:
    assert previous_month_key(today) == expected


def test_current_month_key() -> None:
    assert current_month_key(date(2026, 6, 14)) == "2026-06"


@pytest.mark.parametrize(
    ("month", "start", "end"),
    [
        ("2026-06", date(2026, 6, 1), date(2026, 7, 1)),
        ("2026-12", date(2026, 12, 1), date(2027, 1, 1)),  # year wrap
    ],
)
def test_month_bounds(month: str, start: date, end: date) -> None:
    assert month_bounds(month) == (start, end)


class TestNextQuizAt:
    NY = ZoneInfo("America/New_York")

    def test_none_when_no_weekdays(self) -> None:
        assert (
            next_quiz_at(
                now_utc=datetime(2026, 6, 14, 12, 0, tzinfo=UTC),
                zone=self.NY,
                quiz_time="10:00",
                active_weekdays=[],
            )
            is None
        )

    def test_picks_next_active_weekday(self) -> None:
        # Sunday 2026-06-14 → next Mon(0) at 10:00 EDT == 14:00 UTC on 2026-06-15.
        nxt = next_quiz_at(
            now_utc=datetime(2026, 6, 14, 12, 0, tzinfo=UTC),
            zone=self.NY,
            quiz_time="10:00",
            active_weekdays=[0, 4],
        )
        assert nxt == datetime(2026, 6, 15, 14, 0, tzinfo=UTC)

    def test_same_day_before_time_picks_today(self) -> None:
        # Monday 2026-06-15 08:00 EDT (12:00 UTC) → today 10:00 EDT (14:00 UTC).
        nxt = next_quiz_at(
            now_utc=datetime(2026, 6, 15, 12, 0, tzinfo=UTC),
            zone=self.NY,
            quiz_time="10:00",
            active_weekdays=[0, 4],
        )
        assert nxt == datetime(2026, 6, 15, 14, 0, tzinfo=UTC)

    def test_same_day_after_time_skips_to_next(self) -> None:
        # Monday 16:00 EDT (20:00 UTC) is past 10:00 → next is Friday.
        nxt = next_quiz_at(
            now_utc=datetime(2026, 6, 15, 20, 0, tzinfo=UTC),
            zone=self.NY,
            quiz_time="10:00",
            active_weekdays=[0, 4],
        )
        assert nxt == datetime(2026, 6, 19, 14, 0, tzinfo=UTC)
