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

"""Tests for the ``/v1/me/notification-preferences`` projection helper.

``_prefs_to_items`` is the pure core of both endpoints: it projects the
static registry through a member's stored opt-out map. Pinning it here keeps
the response order/copy tied to the registry and the ``enabled`` flag tied to
the opt-out rule, with no DB/HTTP scaffolding.
"""

from app.api.v1.me import _prefs_to_items
from app.services.notifications import NOTIFICATION_CATEGORIES, NotificationCategory


def test_empty_prefs_render_every_category_enabled() -> None:
    items = _prefs_to_items({})
    assert [i.key for i in items] == [d.category.value for d in NOTIFICATION_CATEGORIES]
    assert all(i.enabled for i in items)


def test_muted_category_renders_disabled_others_stay_on() -> None:
    items = _prefs_to_items({NotificationCategory.MINIGAMES.value: False})
    by_key = {i.key: i for i in items}
    assert by_key[NotificationCategory.MINIGAMES.value].enabled is False
    assert by_key[NotificationCategory.QUIZ.value].enabled is True


def test_items_carry_registry_copy() -> None:
    items = _prefs_to_items({})
    for item, definition in zip(items, NOTIFICATION_CATEGORIES, strict=True):
        assert item.label == definition.label
        assert item.description == definition.description
        assert item.group == definition.group
