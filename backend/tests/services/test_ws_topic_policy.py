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

"""WebSocket topic authorization is default-deny and tenant-scoped."""

import pytest

from app.services.ws_topic_policy import Subscriber, bud_id_of, may_subscribe

ENGINEER = Subscriber(user_id="u1", org_id="o1", has_engineering=True)
SALES = Subscriber(user_id="u2", org_id="o1", has_engineering=False)


@pytest.mark.parametrize(
    "topic",
    ["notifications:u1", "org:o1:install", "xp:u1", "quiz:o1", "agent_activity:o1", "job:abc"],
)
def test_engineer_reaches_own_topics(topic: str) -> None:
    assert may_subscribe(topic, ENGINEER)


@pytest.mark.parametrize(
    "topic",
    ["notifications:u9", "xp:u9", "quiz:o9", "agent_activity:o9", "org:o9:install"],
)
def test_other_users_and_orgs_are_forbidden(topic: str) -> None:
    assert not may_subscribe(topic, ENGINEER)


@pytest.mark.parametrize("topic", ["unknown:o1", "agent_activity", "", "quiz:"])
def test_unknown_or_malformed_topics_are_forbidden(topic: str) -> None:
    assert not may_subscribe(topic, ENGINEER)


def test_people_only_member_keeps_notifications() -> None:
    assert may_subscribe("notifications:u2", SALES)


@pytest.mark.parametrize("topic", ["agent_activity:o1", "quiz:o1", "job:abc", "bud:b1:activity"])
def test_people_only_member_denied_engineering_topics(topic: str) -> None:
    assert not may_subscribe(topic, SALES)


def test_bud_topics_name_the_bud_for_the_ownership_check() -> None:
    assert bud_id_of("bud:b1:activity") == "b1"
    assert bud_id_of("todo:b1") == "b1"
    assert bud_id_of("job:abc") is None
    assert bud_id_of("quiz:o1") is None
