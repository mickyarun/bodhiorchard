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

"""Single source of truth for per-user notification categories.

Every Slack DM the platform sends to a member belongs to exactly one
:class:`NotificationCategory`. A member can mute any category from their
profile; the muted set is stored as ``users.notification_prefs`` (a JSONB
map of ``category -> bool``). Absent keys mean "enabled" — an **opt-out**
model, so a newly-added category is live for everyone until they mute it,
with no data backfill.

To add a future notification type:

1. Add a member to :class:`NotificationCategory`.
2. Add one :class:`CategoryDef` to :data:`NOTIFICATION_CATEGORIES`.
3. Have the sender resolve recipients via
   ``UserRepository.list_slack_recipients(org_id, category=...)``.

That is the entire wiring — the profile UI, the API, and the SQL filter
all read this registry, so nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class NotificationCategory(StrEnum):
    """Stable keys for each opt-out-able notification stream.

    The string value is the persisted key in ``users.notification_prefs``
    and the wire key in the API — never rename one without a migration.
    """

    MINIGAMES = "minigames"
    QUIZ = "quiz"


@dataclass(frozen=True)
class CategoryDef:
    """User-facing metadata for one notification category.

    Attributes:
        category: The stable enum key.
        label: Short title shown next to the profile toggle.
        description: One line explaining what muting this stops.
        group: Heading the profile UI buckets related categories under.
        default_enabled: Whether members receive it before touching settings.
    """

    category: NotificationCategory
    label: str
    description: str
    group: str
    default_enabled: bool = True


# Ordered registry — drives the profile UI listing order. "Games & fun" groups
# the engagement notifications the user asked to make mutable; future
# work/BUD/release notifications would add their own group here.
NOTIFICATION_CATEGORIES: tuple[CategoryDef, ...] = (
    CategoryDef(
        category=NotificationCategory.MINIGAMES,
        label="Mini-game updates",
        description="New garden-game high scores and daily streak nudges.",
        group="Games & fun",
    ),
    CategoryDef(
        category=NotificationCategory.QUIZ,
        label="Company quiz",
        description="Daily quiz-open and answer-reveal reminders.",
        group="Games & fun",
    ),
)

_BY_KEY: dict[str, CategoryDef] = {d.category.value: d for d in NOTIFICATION_CATEGORIES}


def resolve_category(key: str) -> NotificationCategory | None:
    """Return the :class:`NotificationCategory` for a wire key, or ``None``.

    Used by the PATCH endpoint to reject unknown keys instead of silently
    persisting junk that no sender will ever read.
    """
    definition = _BY_KEY.get(key)
    return definition.category if definition else None


def category_default(category: NotificationCategory) -> bool:
    """The shipped default-enabled state for a category (opt-out vs opt-in).

    ``True`` (the registry default) means opt-out — members receive it until
    they mute it. ``False`` means opt-in — members must explicitly enable it.
    The recipient SQL filter is parameterized by this so the in-DB default
    matches the in-Python one.
    """
    definition = _BY_KEY.get(category.value)
    return definition.default_enabled if definition else True


def is_category_enabled(prefs: dict[str, bool] | None, category: NotificationCategory) -> bool:
    """Resolve whether ``category`` is enabled for a member.

    A missing key falls back to the category's :func:`category_default`, so
    the registry — not this function — decides opt-out vs opt-in. Only an
    explicit ``False`` ever mutes. Mirrors the SQL predicate in
    ``UserRepository.list_slack_recipients`` so the in-Python check and the
    DB-side filter never disagree.
    """
    default = category_default(category)
    if not prefs:
        return default
    return prefs.get(category.value, default) is not False


def default_preferences() -> dict[str, bool]:
    """The full default map (per-category ``default_enabled``), for API baselines."""
    return {d.category.value: d.default_enabled for d in NOTIFICATION_CATEGORIES}
