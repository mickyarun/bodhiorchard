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

"""Block Kit payload for the daily celebration digest.

The layout mirrors the shape teams already recognise: a headline, a count
line, one section per celebrant with their avatar as the accessory image,
a divider, and an optional GIF.

Only the day and month of a birthday ever reach this module — see
``EmployeeProfileRepository.list_celebrants``, whose ``Celebrant.years``
is ``None`` for every birthday.
"""

from __future__ import annotations

import calendar
import random
from typing import Any

from app.repositories.employee_profile import Celebrant
from app.services.avatars import absolute_avatar_url

__all__ = [
    "MAX_PERSON_BLOCKS",
    "compose_digest",
    "escape_mrkdwn",
    "fallback_text",
    "format_occasion",
    "ordinal",
]

_BIRTHDAY_HEADLINES = (
    "Whoop Whoop :tada:",
    "Someone's got a birthday :birthday:",
    "Let's make some noise :partying_face:",
)
_ANNIVERSARY_HEADLINES = (
    "Hooray! We've got some serious celebrating to do today!",
    "Another year in the orchard :seedling:",
    "Time to raise a glass :clinking_glasses:",
)
_MIXED_HEADLINE = "Double the reason to celebrate today! :tada:"
_SIGN_OFF = "_Let's break out the balloons, cake, and confetti!_"
_SAMPLE_NOTICE = (
    ":test_tube: *This is a test post* from Bodhiorchard's celebration settings — "
    "nobody's real birthday or anniversary is being announced."
)
# Giphy's API terms require visible attribution next to their content.
_GIPHY_ATTRIBUTION = "Powered by GIPHY"

# Slack rejects an image accessory whose URL is not http(s).
_ALLOWED_SCHEMES = ("http://", "https://")

# Slack rejects a whole message over 50 blocks (``invalid_blocks``). The
# fixed scaffolding is at most 9 blocks (@channel, header, count, sample
# notice, overflow, divider, sign-off, GIF, attribution), so 40 per-person
# sections keeps a huge day comfortably under the cap; everyone beyond that
# is named in a single overflow section instead of being dropped.
MAX_PERSON_BLOCKS = 40
# Slack's limit on a section's text; the overflow list is clipped to it.
_SECTION_TEXT_LIMIT = 3000


def escape_mrkdwn(text: str) -> str:
    """Neutralise Slack's control characters in user-supplied text.

    Slack parses ``<!channel>``, ``<@U123>`` and ``<url|label>`` in both
    ``mrkdwn`` blocks and the top-level ``text``. A name containing them
    would ping the channel or render a disguised link, so ``& < >`` are
    escaped exactly as Slack's formatting guide prescribes.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def ordinal(n: int) -> str:
    """Render ``n`` as an English ordinal: 1 -> 1st, 2 -> 2nd, 11 -> 11th."""
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def format_occasion(celebrant: Celebrant) -> str:
    """The date line under a celebrant's name, e.g. ``October 16``.

    Year-less by construction — :class:`Celebrant` carries no year.
    """
    return f"{calendar.month_name[celebrant.month]} {celebrant.day}"


def _mention(celebrant: Celebrant) -> str:
    """``<@U123>`` when we know their Slack ID, otherwise an escaped bold name."""
    if celebrant.slack_id:
        return f"<@{celebrant.slack_id}>"
    return f"*{escape_mrkdwn(celebrant.name)}*"


def _person_block(celebrant: Celebrant, *, label: str, include_images: bool) -> dict[str, Any]:
    """One section block: mention, occasion label, date, avatar accessory."""
    lines = [_mention(celebrant), label, f"_{format_occasion(celebrant)}_"]
    block: dict[str, Any] = {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(lines)},
    }
    if not include_images:
        return block
    # Slack fetches the image from its own servers, so a photo we host
    # only works when PUBLIC_URL is externally reachable — otherwise this
    # resolves to None and the block simply has no accessory.
    avatar = absolute_avatar_url(celebrant.avatar_url)
    if avatar and avatar.startswith(_ALLOWED_SCHEMES):
        block["accessory"] = {
            "type": "image",
            "image_url": avatar,
            # Slack requires alt_text; it is read out by screen readers.
            # plain text, so no escaping is needed here.
            "alt_text": celebrant.name,
        }
    return block


def _anniversary_label(celebrant: Celebrant) -> str:
    years = celebrant.years or 0
    return f"Work anniversary #{years} :briefcase: — {ordinal(years)} year"


def _overflow_block(rest: list[Celebrant]) -> dict[str, Any]:
    """Name everyone who did not get their own section, within Slack's limit."""
    prefix = f"…and {len(rest)} more to celebrate: "
    text = prefix + ", ".join(_mention(c) for c in rest)
    if len(text) > _SECTION_TEXT_LIMIT:
        text = text[: _SECTION_TEXT_LIMIT - 1] + "…"
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _count_line(birthdays: int, anniversaries: int) -> str:
    """``Today, we are celebrating 1 birthday and 2 work anniversaries:``."""
    parts: list[str] = []
    if birthdays:
        parts.append(f"{birthdays} birthday" + ("s" if birthdays != 1 else ""))
    if anniversaries:
        noun = "work anniversary" if anniversaries == 1 else "work anniversaries"
        parts.append(f"{anniversaries} {noun}")
    return f"Today, we are celebrating {' and '.join(parts)}:"


def _headline(birthdays: int, anniversaries: int) -> str:
    """Pick a headline matching which streams are present."""
    if birthdays and anniversaries:
        return _MIXED_HEADLINE
    pool = _BIRTHDAY_HEADLINES if birthdays else _ANNIVERSARY_HEADLINES
    return random.choice(pool)  # noqa: S311 — cosmetic choice, not security


def fallback_text(
    birthdays: list[Celebrant],
    anniversaries: list[Celebrant],
) -> str:
    """Plain-text summary for notifications and block-render failures.

    Slack parses ``<!channel>``-style control sequences in the top-level
    ``text`` too, so names are escaped here as well.
    """
    names = [escape_mrkdwn(c.name) for c in birthdays + anniversaries]
    return f"Celebrating {', '.join(names)} today!" if names else "Celebrations today!"


def compose_digest(
    birthdays: list[Celebrant],
    anniversaries: list[Celebrant],
    *,
    gif_url: str | None = None,
    mention_channel: bool = False,
    include_images: bool = True,
    sample: bool = False,
) -> list[dict[str, Any]]:
    """Build the Block Kit payload for one day's digest.

    Args:
        birthdays: Birthday celebrants, already filtered and ordered.
        anniversaries: Work-anniversary celebrants; each carries ``years``.
        gif_url: Optional celebratory GIF appended at the bottom.
        mention_channel: Prepend ``@channel``. Off by default — a daily
            broadcast ping is a lot to ask of a busy channel.
        include_images: ``False`` drops every avatar and the GIF. Used to
            retry when Slack rejects the message because it could not fetch
            one of the images — a text-only post beats no post.
        sample: Label the post as a settings test, not a real announcement.

    Returns:
        A Block Kit block list — never more than Slack's 50-block cap.
        Empty when there is nobody to celebrate, which the caller treats as
        "post nothing".
    """
    if not birthdays and not anniversaries:
        return []

    blocks: list[dict[str, Any]] = []
    if mention_channel and not sample:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "<!channel>"}})
    if sample:
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": _SAMPLE_NOTICE}]}
        )

    blocks.append(
        {
            "type": "header",
            # header blocks are plain_text only — no mrkdwn, no emoji syntax
            # unless emoji is enabled explicitly.
            "text": {
                "type": "plain_text",
                "text": _headline(len(birthdays), len(anniversaries)),
                "emoji": True,
            },
        }
    )
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": _count_line(len(birthdays), len(anniversaries)),
                }
            ],
        }
    )

    people: list[tuple[Celebrant, str]] = [(c, "Birthday :birthday:") for c in birthdays]
    people += [(c, _anniversary_label(c)) for c in anniversaries]
    for celebrant, label in people[:MAX_PERSON_BLOCKS]:
        blocks.append(_person_block(celebrant, label=label, include_images=include_images))
    if len(people) > MAX_PERSON_BLOCKS:
        blocks.append(_overflow_block([c for c, _ in people[MAX_PERSON_BLOCKS:]]))

    blocks.append({"type": "divider"})
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": _SIGN_OFF}})

    if gif_url and include_images:
        blocks.append(
            {
                "type": "image",
                "image_url": gif_url,
                "alt_text": "celebration",
            }
        )
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": _GIPHY_ATTRIBUTION}],
            }
        )
    return blocks
