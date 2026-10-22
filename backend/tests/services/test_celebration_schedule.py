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

"""Unit tests for celebration scheduling: fire gate and weekend coverage.

The ``covered_dates`` tests double as the specification for the three
weekend policies — read them before changing that function.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.schemas.settings import CelebrationSettings
from app.schemas.settings import CelebrationWeekendPolicy as Policy
from app.services.celebrations.schedule import (
    MAX_SPAN_DAYS,
    compute_post_window,
    covered_dates,
)

LONDON = ZoneInfo("Europe/London")
WEEKDAYS = [0, 1, 2, 3, 4]  # Mon-Fri

# 2026-10-19 is a Monday; 2026-10-23 the Friday of that week.
MONDAY = date(2026, 10, 19)
TUESDAY = date(2026, 10, 20)
FRIDAY = date(2026, 10, 23)
SATURDAY = date(2026, 10, 24)
SUNDAY = date(2026, 10, 25)


class TestCoveredDatesSkip:
    def test_only_the_post_date(self) -> None:
        assert covered_dates(MONDAY, active_weekdays=WEEKDAYS, policy=Policy.SKIP) == (MONDAY,)

    def test_friday_does_not_reach_the_weekend(self) -> None:
        assert covered_dates(FRIDAY, active_weekdays=WEEKDAYS, policy=Policy.SKIP) == (FRIDAY,)


class TestCoveredDatesRollForward:
    def test_monday_picks_up_the_weekend_behind_it(self) -> None:
        # Sat 24th and Sun 25th roll into Mon 26th.
        assert covered_dates(
            date(2026, 10, 26), active_weekdays=WEEKDAYS, policy=Policy.ROLL_FORWARD
        ) == (SATURDAY, SUNDAY, date(2026, 10, 26))

    def test_midweek_day_covers_only_itself(self) -> None:
        assert covered_dates(TUESDAY, active_weekdays=WEEKDAYS, policy=Policy.ROLL_FORWARD) == (
            TUESDAY,
        )

    def test_result_is_ascending_and_contains_the_post_date(self) -> None:
        got = covered_dates(
            date(2026, 10, 26), active_weekdays=WEEKDAYS, policy=Policy.ROLL_FORWARD
        )
        assert list(got) == sorted(got)
        assert date(2026, 10, 26) in got


class TestCoveredDatesRollBackward:
    def test_friday_celebrates_the_weekend_early(self) -> None:
        assert covered_dates(FRIDAY, active_weekdays=WEEKDAYS, policy=Policy.ROLL_BACKWARD) == (
            FRIDAY,
            SATURDAY,
            SUNDAY,
        )

    def test_midweek_day_covers_only_itself(self) -> None:
        assert covered_dates(TUESDAY, active_weekdays=WEEKDAYS, policy=Policy.ROLL_BACKWARD) == (
            TUESDAY,
        )


class TestCoveredDatesEdges:
    def test_every_day_active_means_no_spill(self) -> None:
        for policy in Policy:
            assert covered_dates(
                SATURDAY, active_weekdays=[0, 1, 2, 3, 4, 5, 6], policy=policy
            ) == (SATURDAY,)

    def test_a_sparse_schedule_is_capped(self) -> None:
        # "Mondays only" would otherwise make one post carry a whole week
        # (roll-forward) — MAX_SPAN_DAYS stops it running away.
        got = covered_dates(MONDAY, active_weekdays=[0], policy=Policy.ROLL_FORWARD)
        assert len(got) <= MAX_SPAN_DAYS + 1
        assert MONDAY in got

    def test_no_date_is_covered_twice_across_a_week(self) -> None:
        # The property that matters in production: with roll-forward, every
        # calendar date in a week is announced exactly once across that
        # week's posts — nobody is skipped, nobody is announced twice.
        seen: list[date] = []
        for offset in range(7):
            day = MONDAY.fromordinal(MONDAY.toordinal() + offset)
            if day.weekday() not in WEEKDAYS:
                continue
            seen.extend(covered_dates(day, active_weekdays=WEEKDAYS, policy=Policy.ROLL_FORWARD))
        assert len(seen) == len(set(seen)), f"duplicate coverage: {seen}"


class TestComputePostWindow:
    def _window(self, now_utc: datetime, **kw):
        params = {
            "zone": LONDON,
            "post_time": "09:30",
            "active_weekdays": WEEKDAYS,
            "policy": Policy.ROLL_FORWARD,
        }
        params.update(kw)
        return compute_post_window(now_utc=now_utc, **params)

    def test_inactive_weekday_returns_none(self) -> None:
        # 2026-10-24 is a Saturday.
        assert self._window(datetime(2026, 10, 24, 12, 0, tzinfo=UTC)) is None

    def test_before_local_post_time_returns_none(self) -> None:
        # Monday 08:00 UTC = 09:00 BST — before 09:30 local.
        assert self._window(datetime(2026, 10, 19, 8, 0, tzinfo=UTC)) is None

    def test_at_or_after_post_time_fires(self) -> None:
        window = self._window(datetime(2026, 10, 19, 9, 0, tzinfo=UTC))
        assert window is not None
        assert window.post_date == MONDAY

    def test_post_at_is_the_local_fire_instant_in_utc(self) -> None:
        # 2026-10-19 is BST (UTC+1), so 09:30 local is 08:30 UTC.
        window = self._window(datetime(2026, 10, 19, 10, 0, tzinfo=UTC))
        assert window is not None
        assert window.post_at == datetime(2026, 10, 19, 8, 30, tzinfo=UTC)

    def test_after_the_dst_switch_the_offset_changes(self) -> None:
        # The UK leaves BST on 2026-10-25, so 09:30 on Mon 26th is 09:30 UTC.
        window = self._window(datetime(2026, 10, 26, 10, 0, tzinfo=UTC))
        assert window is not None
        assert window.post_at == datetime(2026, 10, 26, 9, 30, tzinfo=UTC)


class TestShippedDefault:
    """The default schedule announces every celebration on the day it falls."""

    def test_default_posts_every_day(self) -> None:
        assert CelebrationSettings().active_weekdays == [0, 1, 2, 3, 4, 5, 6]

    def test_weekend_celebration_fires_on_the_weekend(self) -> None:
        defaults = CelebrationSettings()
        window = compute_post_window(
            # Saturday 09:00 UTC = 10:00 BST, inside the 09:30 post window.
            now_utc=datetime(2026, 10, 24, 9, 0, tzinfo=UTC),
            zone=LONDON,
            post_time=defaults.post_time,
            active_weekdays=defaults.active_weekdays,
            policy=defaults.weekend_policy,
        )
        assert window is not None
        assert window.post_date == SATURDAY

    def test_default_schedule_never_rolls(self) -> None:
        # Every day is a posting day, so each post covers exactly itself —
        # no date is announced early, late, or twice.
        defaults = CelebrationSettings()
        for offset in range(7):
            day = MONDAY.fromordinal(MONDAY.toordinal() + offset)
            assert covered_dates(
                day,
                active_weekdays=defaults.active_weekdays,
                policy=defaults.weekend_policy,
            ) == (day,)


class TestPostWindowCap:
    """A digest never goes out hours late, e.g. after an evening restart."""

    def _window(self, now_utc: datetime):
        return compute_post_window(
            now_utc=now_utc,
            zone=LONDON,
            post_time="09:30",
            active_weekdays=WEEKDAYS,
            policy=Policy.ROLL_FORWARD,
        )

    def test_fires_up_to_the_end_of_the_window(self) -> None:
        # 09:30 BST + 3h = 12:30 BST = 11:30 UTC.
        assert self._window(datetime(2026, 10, 19, 11, 30, tzinfo=UTC)) is not None

    def test_does_not_fire_after_the_window(self) -> None:
        assert self._window(datetime(2026, 10, 19, 11, 31, tzinfo=UTC)) is None

    def test_late_evening_restart_does_not_post(self) -> None:
        # 23:40 BST on a posting day — well past post_time.
        assert self._window(datetime(2026, 10, 19, 22, 40, tzinfo=UTC)) is None
