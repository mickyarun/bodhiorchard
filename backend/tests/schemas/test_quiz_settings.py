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

"""Unit tests for QuizGameSettings + the get_quiz_settings resolver.

Pure Pydantic / pure function — no database. Guards the validation that gates
every PATCH /v1/settings/quiz request and the defaulting that the cross-org
scheduler sweep depends on.
"""

import pytest
from pydantic import ValidationError

from app.models.quiz_question import QuizDifficulty, QuizQuestionType
from app.schemas.settings import QuizGameSettings
from app.services.org_settings import DEFAULT_QUIZ_SETTINGS, get_quiz_settings


class TestQuizGameSettingsDefaults:
    """Defaults: enabled, Mon+Fri, 10:00, all three types, 1.0 SP."""

    def test_default_construction(self) -> None:
        s = QuizGameSettings()
        assert s.enabled is True
        assert s.active_weekdays == [0, 4]
        assert s.quiz_time == "10:00"
        assert s.timezone is None
        assert s.window_minutes == 480
        assert s.speed_grace_minutes == 60
        assert s.difficulty == QuizDifficulty.MEDIUM
        assert s.enabled_question_types == [
            QuizQuestionType.MULTIPLE_CHOICE,
            QuizQuestionType.SCRAMBLE,
            QuizQuestionType.FILL_BLANK,
        ]
        assert s.batch_lead_days == 3
        assert s.low_queue_nudge_threshold == 2
        assert s.slack_notify_open is True
        assert s.slack_notify_reveal is False
        assert s.monthly_sp_amount == 1.0

    def test_round_trip_snake_case(self) -> None:
        persisted = QuizGameSettings().model_dump(by_alias=False)
        assert QuizGameSettings(**persisted) == QuizGameSettings()

    def test_round_trip_camel_case(self) -> None:
        envelope = QuizGameSettings().model_dump(by_alias=True)
        assert "activeWeekdays" in envelope
        assert "enabledQuestionTypes" in envelope
        assert "monthlySpAmount" in envelope
        assert QuizGameSettings(**envelope) == QuizGameSettings()


class TestQuizGameSettingsValidation:
    """Fail-fast validation for every externally-settable field."""

    def test_empty_weekdays_rejected(self) -> None:
        with pytest.raises(ValidationError):
            QuizGameSettings(active_weekdays=[])

    @pytest.mark.parametrize("bad_day", [-1, 7, 99])
    def test_out_of_range_weekday_rejected(self, bad_day: int) -> None:
        with pytest.raises(ValidationError):
            QuizGameSettings(active_weekdays=[bad_day])

    def test_weekdays_deduped_and_sorted(self) -> None:
        s = QuizGameSettings(active_weekdays=[4, 0, 4, 2])
        assert s.active_weekdays == [0, 2, 4]

    @pytest.mark.parametrize("bad_time", ["9:00", "24:00", "10:60", "abc", "10"])
    def test_invalid_quiz_time_rejected(self, bad_time: str) -> None:
        with pytest.raises(ValidationError):
            QuizGameSettings(quiz_time=bad_time)

    def test_unknown_timezone_rejected(self) -> None:
        with pytest.raises(ValidationError):
            QuizGameSettings(timezone="Mars/Olympus")

    def test_known_timezone_accepted(self) -> None:
        assert QuizGameSettings(timezone="America/New_York").timezone == "America/New_York"

    @pytest.mark.parametrize(
        ("field", "bad"),
        [
            ("window_minutes", 14),
            ("window_minutes", 1441),
            ("speed_grace_minutes", 0),
            ("batch_lead_days", 15),
            ("low_queue_nudge_threshold", 31),
            ("monthly_sp_amount", -0.5),
            ("monthly_sp_amount", 10.5),
        ],
    )
    def test_numeric_bounds(self, field: str, bad: float) -> None:
        with pytest.raises(ValidationError):
            QuizGameSettings(**{field: bad})

    def test_empty_question_types_rejected(self) -> None:
        with pytest.raises(ValidationError):
            QuizGameSettings(enabled_question_types=[])

    def test_question_types_deduped(self) -> None:
        s = QuizGameSettings(
            enabled_question_types=[
                QuizQuestionType.SCRAMBLE,
                QuizQuestionType.SCRAMBLE,
                QuizQuestionType.MULTIPLE_CHOICE,
            ]
        )
        assert s.enabled_question_types == [
            QuizQuestionType.SCRAMBLE,
            QuizQuestionType.MULTIPLE_CHOICE,
        ]


class TestGetQuizSettings:
    """The single resolver of org.config['quiz'] — defaults + defensive fallback."""

    def test_none_config_returns_defaults(self) -> None:
        assert get_quiz_settings(None) == QuizGameSettings()

    def test_missing_section_returns_defaults(self) -> None:
        assert get_quiz_settings({"presence": {}}) == QuizGameSettings()

    def test_partial_section_fills_defaults(self) -> None:
        s = get_quiz_settings({"quiz": {"enabled": False, "active_weekdays": [1, 3]}})
        assert s.enabled is False
        assert s.active_weekdays == [1, 3]
        assert s.quiz_time == "10:00"  # default filled

    def test_corrupt_section_falls_back_to_defaults(self) -> None:
        """A bad stored value must never abort the cross-org sweep."""
        s = get_quiz_settings({"quiz": {"active_weekdays": [99], "quiz_time": "nope"}})
        assert s == DEFAULT_QUIZ_SETTINGS
