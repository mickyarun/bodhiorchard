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

"""Unit tests for the notification-category registry.

These pin the *opt-out* contract: only an explicit ``False`` mutes a
category, so every current and future category defaults to enabled. The SQL
recipient filter (``UserRepository.list_slack_recipients``) is asserted to
mirror this exact rule in ``test_user_slack_recipients.py``.
"""

from app.services.notifications import (
    NOTIFICATION_CATEGORIES,
    NotificationCategory,
    category_default,
    default_preferences,
    is_category_enabled,
    resolve_category,
)


def test_absent_prefs_mean_enabled() -> None:
    # A member who never touched settings (None / empty map) gets everything.
    assert is_category_enabled(None, NotificationCategory.MINIGAMES) is True
    assert is_category_enabled({}, NotificationCategory.QUIZ) is True


def test_only_explicit_false_mutes() -> None:
    prefs = {NotificationCategory.MINIGAMES.value: False}
    assert is_category_enabled(prefs, NotificationCategory.MINIGAMES) is False
    # A category the member didn't touch stays enabled.
    assert is_category_enabled(prefs, NotificationCategory.QUIZ) is True


def test_explicit_true_is_enabled() -> None:
    prefs = {NotificationCategory.QUIZ.value: True}
    assert is_category_enabled(prefs, NotificationCategory.QUIZ) is True


def test_default_preferences_covers_every_category_and_is_all_on() -> None:
    defaults = default_preferences()
    assert set(defaults) == {d.category.value for d in NOTIFICATION_CATEGORIES}
    assert all(defaults.values())


def test_resolve_category_accepts_known_keys_and_rejects_junk() -> None:
    assert resolve_category("minigames") is NotificationCategory.MINIGAMES
    assert resolve_category("quiz") is NotificationCategory.QUIZ
    assert resolve_category("not_a_real_category") is None


def test_registry_keys_are_unique() -> None:
    keys = [d.category.value for d in NOTIFICATION_CATEGORIES]
    assert len(keys) == len(set(keys))


def test_category_default_reflects_registry() -> None:
    # Every shipped category is opt-out (default-on) today.
    for definition in NOTIFICATION_CATEGORIES:
        assert category_default(definition.category) is definition.default_enabled


def test_absent_key_falls_back_to_category_default_not_a_hardcoded_true() -> None:
    # The resolver must consult category_default for a missing key, so an
    # opt-in (default-off) category added later resolves to disabled, not on.
    # We assert the wiring by mirroring category_default exactly for an empty map.
    for definition in NOTIFICATION_CATEGORIES:
        category = definition.category
        assert is_category_enabled({}, category) is category_default(category)
