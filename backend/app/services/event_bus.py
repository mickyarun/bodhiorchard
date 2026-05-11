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

"""In-process topic-based event bus with pluggable external transports.

Services publish events to string topics (e.g. "job:{id}", "scan:{id}").

Two consumer kinds are supported side-by-side:

1. **Queue subscribers** — `subscribe(topic)` returns an `asyncio.Queue` that
   the caller reads from. Used by the WebSocket endpoint (`/ws`) to push
   events to dashboard clients.

2. **External transports** — async callbacks registered once at app startup
   via `register_transport(fn)`. Each `publish()` spawns a detached task per
   transport. Transports self-filter by topic prefix. This is how
   `agent_activity:*` events reach the multiplayer server (see
   `colyseus_forwarder.py`).

Queue subscribers and transports are independent: a topic with zero queue
subscribers still fans out to every transport, and vice versa.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

# topic → set of subscriber queues
_subscribers: dict[str, set[asyncio.Queue[dict]]] = {}

#: Signature for a fan-out transport. Transports MUST be non-blocking and
#: never raise — raised exceptions are logged and swallowed so one bad
#: transport can't take down the event bus.
Transport = Callable[[str, dict[str, Any]], Awaitable[None]]

# Registered transports, in registration order.
_transports: list[Transport] = []
# GC anchor for in-flight transport tasks — required because
# `asyncio.create_task` only holds a weak reference (see backend/CLAUDE.md).
_transport_tasks: set[asyncio.Task[None]] = set()


def subscribe(topic: str) -> asyncio.Queue[dict]:
    """Create a queue and register it under *topic*.

    Returns the queue; the caller reads from it to receive events.
    """
    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=settings.ws.max_subscribe_queue)
    _subscribers.setdefault(topic, set()).add(queue)
    # Subscribe logging removed — too noisy at debug level (fires on every page load)
    return queue


def unsubscribe(topic: str, queue: asyncio.Queue[dict]) -> None:
    """Remove *queue* from *topic*. Deletes the topic key if empty."""
    subs = _subscribers.get(topic)
    if subs is None:
        return
    subs.discard(queue)
    if not subs:
        del _subscribers[topic]
    logger.debug("event_bus_unsubscribe", topic=topic, remaining=len(subs) if subs else 0)


def register_transport(transport: Transport) -> None:
    """Register *transport* to be invoked on every `publish()`.

    Idempotent by identity — registering the same callable twice is a no-op,
    which keeps uvicorn --reload from double-firing transports.
    """
    if transport in _transports:
        return
    _transports.append(transport)
    logger.info(
        "event_bus_transport_registered",
        name=getattr(transport, "__name__", repr(transport)),
        total=len(_transports),
    )


def clear_transports() -> None:
    """Remove every registered transport. Intended for tests / shutdown."""
    _transports.clear()


def publish(topic: str, data: dict) -> None:
    """Fan out *data* to queue subscribers AND external transports.

    Queue subscribers receive an envelope `{"topic": topic, "data": data}`.
    External transports receive `(topic, data)` directly and run as detached
    tasks — failures are logged but never propagate.

    Drops the message for any queue that is full (slow consumer catches the
    next update).
    """
    subs = _subscribers.get(topic)
    subscriber_count = len(subs) if subs else 0

    if not subs and not _transports:
        logger.info("event_bus_no_subscribers", topic=topic)

    # In-process queue fanout (unchanged semantics).
    if subs:
        envelope = {"topic": topic, "data": data}
        if "agent_activity" in topic:
            logger.info(
                "event_bus_publish_agent",
                topic=topic,
                event_type=data.get("event_type", ""),
                subscriber_count=subscriber_count,
            )
        for queue in subs:
            try:
                queue.put_nowait(envelope)
            except asyncio.QueueFull:
                logger.warning("event_bus_queue_full", topic=topic)

    # External transport fanout (Colyseus, future Slack/SSE/metrics/etc.).
    for transport in _transports:
        task = asyncio.create_task(_invoke_transport(transport, topic, data))
        _transport_tasks.add(task)
        task.add_done_callback(_transport_tasks.discard)


async def _invoke_transport(transport: Transport, topic: str, data: dict) -> None:
    """Run *transport* and contain any exception it raises."""
    try:
        await transport(topic, data)
    except asyncio.CancelledError:
        raise
    except Exception as err:  # noqa: BLE001
        logger.warning(
            "event_bus_transport_failed",
            transport=getattr(transport, "__name__", repr(transport)),
            topic=topic,
            error=str(err),
        )


def cleanup_topic(topic: str) -> None:
    """Remove all subscribers for *topic*."""
    removed = _subscribers.pop(topic, None)
    if removed:
        logger.debug("event_bus_cleanup_topic", topic=topic, removed_count=len(removed))
