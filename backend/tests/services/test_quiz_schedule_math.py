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

"""Unit tests for the pure quiz schedule math (weekday gate, fire instants, DST)."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.services.quiz_schedule_math import compute_open_window

# Monday 2026-06-01 and Friday 2026-06-05 are the default active weekdays.
NY = ZoneInfo("America/New_York")


def _window(now_utc: datetime, **kw):
    params = {
        "zone": NY,
        "quiz_time": "10:00",
        "active_weekdays": [0, 4],  # Mon, Fri
        "window_minutes": 480,
    }
    params.update(kw)
    return compute_open_window(now_utc=now_utc, **params)


class TestWeekdayGate:
    def test_inactive_weekday_returns_none(self) -> None:
        # 2026-06-02 is a Tuesday — not in [Mon, Fri].
        assert _window(datetime(2026, 6, 2, 14, 0, tzinfo=UTC)) is None

    def test_active_weekday_before_time_returns_none(self) -> None:
        # Monday 2026-06-01, 13:00 UTC = 09:00 EDT — before 10:00 local.
        assert _window(datetime(2026, 6, 1, 13, 0, tzinfo=UTC)) is None

    def test_active_weekday_at_time_fires(self) -> None:
        # Monday 14:00 UTC = 10:00 EDT exactly.
        w = _window(datetime(2026, 6, 1, 14, 0, tzinfo=UTC))
        assert w is not None
        assert w.quiz_date.isoformat() == "2026-06-01"

    def test_fires_when_past_time_missed_tick(self) -> None:
        # 15:30 UTC = 11:30 EDT — well past 10:00; a missed minute still fires.
        w = _window(datetime(2026, 6, 1, 15, 30, tzinfo=UTC))
        assert w is not None


class TestWindowInstants:
    def test_open_and_reveal_are_utc_and_spaced(self) -> None:
        w = _window(datetime(2026, 6, 1, 14, 0, tzinfo=UTC), window_minutes=480)
        assert w is not None
        # 10:00 EDT == 14:00 UTC.
        assert w.open_at == datetime(2026, 6, 1, 14, 0, tzinfo=UTC)
        # +480 minutes = 8h.
        assert w.reveal_at == datetime(2026, 6, 1, 22, 0, tzinfo=UTC)


class TestTimezoneCorrectness:
    def test_local_date_used_not_utc_date(self) -> None:
        # Tokyo: Friday 2026-06-05 10:00 JST == 2026-06-05 01:00 UTC.
        tokyo = ZoneInfo("Asia/Tokyo")
        w = _window(datetime(2026, 6, 5, 1, 0, tzinfo=UTC), zone=tokyo)
        assert w is not None
        assert w.quiz_date.isoformat() == "2026-06-05"
        assert w.open_at == datetime(2026, 6, 5, 1, 0, tzinfo=UTC)

    def test_utc_evening_can_be_next_local_day(self) -> None:
        # Tokyo Thursday 23:00 UTC == Friday 08:00 JST — before 10:00, no fire.
        tokyo = ZoneInfo("Asia/Tokyo")
        assert _window(datetime(2026, 6, 4, 23, 0, tzinfo=UTC), zone=tokyo) is None
