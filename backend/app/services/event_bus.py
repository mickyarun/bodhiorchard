"""In-process topic-based event bus for real-time push.

Services publish events to string topics (e.g. "job:{id}", "scan:{id}").
WebSocket connections subscribe to topics and receive events via asyncio.Queue.
"""

import asyncio

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

# topic → set of subscriber queues
_subscribers: dict[str, set[asyncio.Queue[dict]]] = {}


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


def publish(topic: str, data: dict) -> None:
    """Fan out *data* to every subscriber queue for *topic*.

    Wraps data in an envelope: ``{"topic": topic, "data": data}``.
    Drops the message for any queue that is full (slow consumer
    catches the next update).
    """
    subs = _subscribers.get(topic)
    if not subs:
        logger.info("event_bus_no_subscribers", topic=topic)
        return
    envelope = {"topic": topic, "data": data}
    event_type = data.get("event_type", "")
    if "agent_activity" in topic:
        logger.info(
            "event_bus_publish_agent",
            topic=topic,
            event_type=event_type,
            subscriber_count=len(subs),
        )
    for queue in subs:
        try:
            queue.put_nowait(envelope)
        except asyncio.QueueFull:
            logger.warning("event_bus_queue_full", topic=topic)


def cleanup_topic(topic: str) -> None:
    """Remove all subscribers for *topic*."""
    removed = _subscribers.pop(topic, None)
    if removed:
        logger.debug("event_bus_cleanup_topic", topic=topic, removed_count=len(removed))
