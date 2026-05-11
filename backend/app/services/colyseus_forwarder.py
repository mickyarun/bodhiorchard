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

"""Event-bus transport that forwards agent_activity events to the multiplayer server.

Registered once at FastAPI startup (see `app.main.lifespan`). From there,
every `event_bus.publish("agent_activity:<org_id>", ...)` call triggers
this transport as a detached task, which fire-and-forgets an HTTP POST
into the Colyseus bridge.

This module is intentionally small and pure: no side effects at import
time, no state held between calls. One of potentially several external
transports the event bus may fan out to — treat it as a template when
adding new destinations (Slack, metrics exporters, SSE bridges, …).
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from app.services.colyseus_bridge import publish_to_colyseus

logger = structlog.get_logger(__name__)

_AGENT_ACTIVITY_PREFIX = "agent_activity:"


async def forward_agent_activity_to_colyseus(
    topic: str,
    payload: dict[str, Any],
) -> None:
    """Forward an `agent_activity:<org_id>` publish to the Colyseus bridge.

    Non-matching topics are silently ignored (the event bus fans out to
    every registered transport regardless of topic; each transport
    self-filters).

    Bad UUIDs are logged and dropped rather than crashing the caller —
    the event bus swallows transport exceptions, but logging the reason
    here is cheaper than reconstructing it from a stack trace.
    """
    if not topic.startswith(_AGENT_ACTIVITY_PREFIX):
        return

    org_id_str = topic[len(_AGENT_ACTIVITY_PREFIX) :]
    try:
        org_id = uuid.UUID(org_id_str)
    except ValueError:
        logger.warning(
            "colyseus_forwarder_bad_org_id",
            topic=topic,
            org_id_str=org_id_str,
        )
        return

    await publish_to_colyseus(org_id, "agent_activity", payload)
