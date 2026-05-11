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

"""Unit tests for the PresenceSettings Pydantic schema.

These tests are pure Pydantic — no database, no fixtures. They guard the
validation rules that gate every PATCH /v1/settings/connections request
that touches the presence section.

Preserved invariants:
    * Defaults match the legacy hardcoded behaviour (Mon-Fri, 08:00-18:00,
      timezone None) so un-migrated orgs see no change.
    * ``working_days`` must be non-empty.
    * ``working_hours_*`` must match ``HH:MM`` (24-hour) and start < end.
    * ``timezone`` must be a valid IANA name or None.
    * camelCase alias round-trips cleanly through ``model_dump(by_alias=True)``.
"""

import pytest
from pydantic import ValidationError

from app.schemas.settings import PresenceSettings


class TestPresenceSettingsDefaults:
    """Defaults must preserve current ``InferredPresenceSim`` behaviour."""

    def test_default_construction_has_legacy_values(self) -> None:
        """An empty construction returns Mon-Fri, 08:00-18:00, tz=None."""
        settings = PresenceSettings()
        assert settings.auto_mode_enabled is True
        assert settings.working_days == ["mon", "tue", "wed", "thu", "fri"]
        assert settings.working_hours_start == "08:00"
        assert settings.working_hours_end == "18:00"
        assert settings.timezone is None

    def test_round_trip_snake_case(self) -> None:
        """Persisted JSON (snake_case) must reparse without change."""
        persisted = PresenceSettings().model_dump(by_alias=False)
        reparsed = PresenceSettings(**persisted)
        assert reparsed == PresenceSettings()

    def test_round_trip_camel_case(self) -> None:
        """API envelope (camelCase) must reparse via populate_by_name."""
        envelope = PresenceSettings().model_dump(by_alias=True)
        assert "autoModeEnabled" in envelope
        assert "workingDays" in envelope
        assert "workingHoursStart" in envelope
        assert "workingHoursEnd" in envelope
        reparsed = PresenceSettings(**envelope)
        assert reparsed == PresenceSettings()


class TestPresenceSettingsValidation:
    """Fail-fast validation for every externally-settable field."""

    def test_empty_working_days_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PresenceSettings(working_days=[])

    def test_unknown_weekday_rejected(self) -> None:
        with pytest.raises(ValidationError):
            # "MON" in uppercase is not in the Literal whitelist.
            PresenceSettings(working_days=["MON"])  # type: ignore[list-item]

    @pytest.mark.parametrize(
        "bad_time",
        ["9:00", "24:00", "08:60", "abc", "08", "08:0a"],
    )
    def test_invalid_hhmm_rejected(self, bad_time: str) -> None:
        with pytest.raises(ValidationError):
            PresenceSettings(working_hours_start=bad_time)
        with pytest.raises(ValidationError):
            PresenceSettings(working_hours_end=bad_time)

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            ("18:00", "08:00"),  # reverse
            ("12:00", "12:00"),  # equal
            ("17:30", "09:00"),  # reverse with minutes
        ],
    )
    def test_start_must_be_before_end(self, start: str, end: str) -> None:
        with pytest.raises(ValidationError):
            PresenceSettings(working_hours_start=start, working_hours_end=end)

    def test_unknown_timezone_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PresenceSettings(timezone="Mars/Olympus")

    def test_known_timezone_accepted(self) -> None:
        settings = PresenceSettings(timezone="Asia/Kolkata")
        assert settings.timezone == "Asia/Kolkata"

    @pytest.mark.parametrize("legacy_alias", ["Asia/Calcutta", "US/Eastern", "GB"])
    def test_legacy_iana_alias_accepted(self, legacy_alias: str) -> None:
        """Browsers on older ICU still emit ``backward`` aliases — regression
        for prod failure where Debian-slim's tzdata omits these."""
        assert PresenceSettings(timezone=legacy_alias).timezone == legacy_alias

    def test_null_timezone_accepted(self) -> None:
        """None is the legacy sentinel — must always pass through."""
        assert PresenceSettings(timezone=None).timezone is None


class TestPresenceSettingsSaturdayOffice:
    """The original user story: a company with a Saturday office."""

    def test_saturday_working_day(self) -> None:
        settings = PresenceSettings(
            working_days=["mon", "tue", "wed", "thu", "fri", "sat"],
            working_hours_start="09:00",
            working_hours_end="17:30",
            timezone="Asia/Kolkata",
        )
        assert "sat" in settings.working_days
        assert settings.timezone == "Asia/Kolkata"

    def test_night_shift(self) -> None:
        """Non-standard hours like an evening shift must validate."""
        settings = PresenceSettings(
            working_hours_start="14:00",
            working_hours_end="22:00",
        )
        assert settings.working_hours_start == "14:00"
        assert settings.working_hours_end == "22:00"
