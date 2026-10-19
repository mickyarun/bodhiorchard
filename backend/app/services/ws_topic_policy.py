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

"""Which WebSocket topics a connection may subscribe to.

Default-deny: a topic is allowed only if its prefix is listed here. Each
prefix declares who may read it:

* ``user`` — the second segment must be the caller's own user id.
* ``org`` — the second segment must be the caller's own org id.
* ``id`` — addressed by an opaque UUID (a job, scan or BUD). Ownership
  isn't checked per subscription; the UUID is the capability.

``engineering`` marks topics that carry engineering-workspace data and so
need ``workspace:engineering``. Adding a new publisher means adding its
prefix here, or no client will ever receive it.
"""

from dataclasses import dataclass
from typing import Literal

Scope = Literal["user", "org", "id"]


@dataclass(frozen=True)
class TopicRule:
    """Access rule for one topic prefix."""

    scope: Scope
    engineering: bool


TOPIC_RULES: dict[str, TopicRule] = {
    "notifications": TopicRule(scope="user", engineering=False),
    "org": TopicRule(scope="org", engineering=False),
    "xp": TopicRule(scope="user", engineering=True),
    "yield_offer": TopicRule(scope="user", engineering=True),
    "quiz": TopicRule(scope="org", engineering=True),
    "agent_activity": TopicRule(scope="org", engineering=True),
    "job": TopicRule(scope="id", engineering=True),
    "scan": TopicRule(scope="id", engineering=True),
    "scan_synthesis_tool": TopicRule(scope="id", engineering=True),
    "todo": TopicRule(scope="id", engineering=True),
    "bud": TopicRule(scope="id", engineering=True),
}


@dataclass(frozen=True)
class Subscriber:
    """Identity of a WebSocket connection, resolved once at connect."""

    user_id: str
    org_id: str
    has_engineering: bool


def may_subscribe(topic: str, who: Subscriber) -> bool:
    """Return True if ``who`` may subscribe to ``topic``."""
    prefix, _, rest = topic.partition(":")
    rule = TOPIC_RULES.get(prefix)
    if rule is None or not rest:
        return False
    if rule.engineering and not who.has_engineering:
        return False
    owner = rest.split(":", 1)[0]
    if rule.scope == "user":
        return owner == who.user_id
    if rule.scope == "org":
        return owner == who.org_id
    return True
