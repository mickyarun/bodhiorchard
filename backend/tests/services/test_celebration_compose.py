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

"""Unit tests for the celebration digest Block Kit composer."""

import dataclasses
import json
import uuid

import pytest

from app.config import settings
from app.repositories.employee_profile import Celebrant
from app.services.celebrations.compose import (
    MAX_PERSON_BLOCKS,
    compose_digest,
    escape_mrkdwn,
    fallback_text,
    format_occasion,
    ordinal,
)


def _person(
    name: str = "Sid",
    *,
    years: int | None = None,
    month: int = 10,
    day: int = 16,
    slack_id: str | None = "U123",
    avatar: str | None = None,
) -> Celebrant:
    return Celebrant(
        user_id=uuid.uuid4(),
        name=name,
        avatar_url=avatar,
        slack_id=slack_id,
        month=month,
        day=day,
        years=years,
    )


def _all_text(blocks: list[dict]) -> str:
    """Every string anywhere in the payload, for substring assertions."""
    return json.dumps(blocks)


class TestOrdinal:
    def test_small_numbers(self) -> None:
        assert [ordinal(n) for n in (1, 2, 3, 4)] == ["1st", "2nd", "3rd", "4th"]

    def test_teens_are_th(self) -> None:
        # The classic off-by-one: 11/12/13 are NOT 11st/12nd/13rd.
        assert [ordinal(n) for n in (11, 12, 13)] == ["11th", "12th", "13th"]

    def test_twenties_resume_suffixes(self) -> None:
        assert [ordinal(n) for n in (21, 22, 23)] == ["21st", "22nd", "23rd"]


class TestFormatOccasion:
    def test_month_name_and_day(self) -> None:
        assert format_occasion(_person(month=10, day=16)) == "October 16"

    def test_single_digit_day_is_not_zero_padded(self) -> None:
        assert format_occasion(_person(month=3, day=5)) == "March 5"

    def test_leap_day_keeps_february_29(self) -> None:
        assert format_occasion(_person(month=2, day=29)) == "February 29"


class TestCelebrantCarriesNoYear:
    def test_no_field_can_hold_a_date(self) -> None:
        # The birth-year guarantee is structural: Celebrant has no date-typed
        # field a future consumer could log or serialise.
        types = {f.name: f.type for f in dataclasses.fields(Celebrant)}
        assert not any("date" in str(t) for t in types.values()), types


class TestEscapeMrkdwn:
    def test_control_sequences_are_neutralised(self) -> None:
        assert escape_mrkdwn("<!channel> & <https://x|y>") == (
            "&lt;!channel&gt; &amp; &lt;https://x|y&gt;"
        )

    def test_hostile_name_cannot_ping_the_channel(self) -> None:
        blocks = compose_digest([_person("<!channel>", slack_id=None)], [])
        payload = _all_text(blocks)
        assert "<!channel>" not in payload
        assert "&lt;!channel&gt;" in payload

    def test_fallback_text_is_escaped_too(self) -> None:
        text = fallback_text([_person("<!here>", slack_id=None)], [])
        assert "<!here>" not in text


class TestComposeDigest:
    def test_empty_input_produces_no_blocks(self) -> None:
        assert compose_digest([], []) == []

    def test_anniversary_shows_the_completed_count(self) -> None:
        blocks = compose_digest([], [_person("Michael", years=1)])
        payload = _all_text(blocks)
        assert "Work anniversary #1" in payload
        assert "1st year" in payload

    def test_counts_are_pluralised(self) -> None:
        blocks = compose_digest([_person("A"), _person("B")], [_person("C", years=3)])
        assert "2 birthdays and 1 work anniversary:" in _all_text(blocks)

    def test_singular_birthday_count(self) -> None:
        blocks = compose_digest([_person()], [])
        assert "1 birthday:" in _all_text(blocks)

    def test_slack_id_becomes_a_mention(self) -> None:
        blocks = compose_digest([_person(slack_id="UABC")], [])
        assert "<@UABC>" in _all_text(blocks)

    def test_unlinked_member_falls_back_to_bold_name(self) -> None:
        blocks = compose_digest([_person("Priya", slack_id=None)], [])
        payload = _all_text(blocks)
        assert "*Priya*" in payload
        assert "<@" not in payload

    def test_absolute_avatar_becomes_an_accessory(self) -> None:
        blocks = compose_digest([_person(avatar="https://avatars.slack-edge.com/x.png")], [])
        sections = [b for b in blocks if b.get("accessory")]
        assert len(sections) == 1
        assert sections[0]["accessory"]["type"] == "image"
        # Slack rejects an image accessory without alt_text.
        assert sections[0]["accessory"]["alt_text"]

    def test_unreachable_relative_avatar_is_dropped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A self-hosted photo on a localhost deployment cannot be fetched by
        # Slack, so it must not be emitted as a block that renders broken.
        monkeypatch.setattr(settings, "public_url", "http://localhost:8000")
        blocks = compose_digest([_person(avatar="/api/v1/employees/avatars/k")], [])
        assert not any(b.get("accessory") for b in blocks)

    def test_reachable_relative_avatar_is_made_absolute(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "public_url", "https://bodhi.example.com")
        blocks = compose_digest([_person(avatar="/api/v1/employees/avatars/k")], [])
        accessory = next(b["accessory"] for b in blocks if b.get("accessory"))
        assert accessory["image_url"] == "https://bodhi.example.com/api/v1/employees/avatars/k"

    def test_channel_mention_is_opt_in(self) -> None:
        assert "<!channel>" not in _all_text(compose_digest([_person()], []))
        assert "<!channel>" in _all_text(compose_digest([_person()], [], mention_channel=True))

    def test_gif_is_shown_with_giphy_attribution(self) -> None:
        blocks = compose_digest([_person()], [], gif_url="https://media.giphy.com/a.gif")
        assert blocks[-2]["type"] == "image"
        assert blocks[-2]["image_url"] == "https://media.giphy.com/a.gif"
        # Giphy's API terms require visible attribution.
        assert "Powered by GIPHY" in _all_text(blocks[-1:])

    def test_no_gif_block_without_a_url(self) -> None:
        blocks = compose_digest([_person()], [])
        assert not any(b["type"] == "image" for b in blocks)
        assert "GIPHY" not in _all_text(blocks)

    def test_header_block_uses_plain_text(self) -> None:
        # Slack rejects a header block whose text type is mrkdwn.
        header = next(b for b in compose_digest([_person()], []) if b["type"] == "header")
        assert header["text"]["type"] == "plain_text"


class TestTextOnly:
    def test_drops_every_image(self) -> None:
        blocks = compose_digest(
            [_person(avatar="https://avatars.slack-edge.com/x.png")],
            [],
            gif_url="https://media.giphy.com/a.gif",
            include_images=False,
        )
        assert not any(b.get("accessory") for b in blocks)
        assert not any(b["type"] == "image" for b in blocks)


class TestSlackBlockLimit:
    def test_huge_day_stays_under_fifty_blocks(self) -> None:
        crowd = [_person(f"P{i}", slack_id=f"U{i}") for i in range(120)]
        blocks = compose_digest(
            crowd,
            [_person("A", years=2)],
            gif_url="https://media.giphy.com/a.gif",
            mention_channel=True,
        )
        assert len(blocks) <= 50

    def test_nobody_is_dropped_by_the_cap(self) -> None:
        crowd = [_person(f"P{i}", slack_id=f"U{i}") for i in range(MAX_PERSON_BLOCKS + 5)]
        payload = _all_text(compose_digest(crowd, []))
        for i in range(MAX_PERSON_BLOCKS + 5):
            assert f"<@U{i}>" in payload
        assert "and 5 more to celebrate" in payload

    def test_overflow_text_respects_section_limit(self) -> None:
        crowd = [_person("x" * 80, slack_id=None) for _ in range(MAX_PERSON_BLOCKS + 200)]
        blocks = compose_digest(crowd, [])
        assert all(len(b.get("text", {}).get("text", "")) <= 3000 for b in blocks)


class TestSample:
    def test_sample_is_labelled_and_never_pings_the_channel(self) -> None:
        blocks = compose_digest([_person()], [], mention_channel=True, sample=True)
        payload = _all_text(blocks)
        assert "This is a test post" in payload
        assert "<!channel>" not in payload


class TestFallbackText:
    def test_lists_every_name(self) -> None:
        text = fallback_text([_person("Sid")], [_person("Michael", years=2)])
        assert "Sid" in text
        assert "Michael" in text

    def test_handles_nobody(self) -> None:
        assert fallback_text([], [])
