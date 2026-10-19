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

"""Multiplexed WebSocket endpoint for real-time push.

A single WS connection per client handles multiple topic subscriptions.
Clients send JSON subscribe/unsubscribe messages; the server pushes
events from the event bus.

Protocol:
    Client → Server:
        {"action": "subscribe", "topic": "job:abc-123"}
        {"action": "unsubscribe", "topic": "job:abc-123"}
        {"action": "ping"}

    Server → Client:
        {"topic": "job:abc-123", "data": {...}}
        {"type": "pong"}
        {"error": "unauthorized"}
"""

import asyncio
import json
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.core.deps import member_has_permission
from app.core.permissions import WORKSPACE_ENGINEERING
from app.core.security import verify_token
from app.database import AsyncSessionLocal
from app.repositories.user import UserRepository
from app.services.event_bus import subscribe, unsubscribe
from app.services.ws_topic_policy import Subscriber, may_subscribe

logger = structlog.get_logger(__name__)

router = APIRouter()


async def _resolve_subscriber(payload: dict[str, Any]) -> Subscriber | None:
    """Resolve the JWT to an active org member, or None to reject the socket.

    Membership and engineering access are read once at connect; a role
    change takes effect on the client's next reconnect.
    """
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
        org_id = uuid.UUID(str(payload.get("org_id")))
    except ValueError:
        return None
    async with AsyncSessionLocal() as db:
        repo = UserRepository(db)
        user = await repo.get_by_id(user_id)
        if user is None or not user.is_active:
            return None
        if not await repo.is_member_of_org(user_id, org_id):
            return None
        has_engineering = await member_has_permission(db, user_id, org_id, WORKSPACE_ENGINEERING)
    return Subscriber(user_id=str(user_id), org_id=str(org_id), has_engineering=has_engineering)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Accept a multiplexed WebSocket connection.

    Query param ``token`` is required for JWT authentication.
    """
    # ── Auth ──────────────────────────────────────────────
    token = websocket.query_params.get("token")
    if not token:
        await websocket.accept()
        await websocket.send_json({"error": "unauthorized"})
        await websocket.close(code=4001)
        return

    payload = verify_token(token)
    who = await _resolve_subscriber(payload) if payload is not None else None
    if who is None:
        await websocket.accept()
        await websocket.send_json({"error": "unauthorized"})
        await websocket.close(code=4001)
        return

    await websocket.accept()
    user_id = who.user_id
    logger.debug("ws_connected", user_id=user_id, org_id=who.org_id)

    # ── State per connection ──────────────────────────────
    # topic → (event_bus queue, reader task)
    subscriptions: dict[str, tuple[asyncio.Queue[dict[str, Any]], asyncio.Task[None]]] = {}
    send_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=settings.ws.max_send_queue)

    async def _topic_reader(topic: str, bus_queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Read from an event bus queue and forward into the send queue."""
        try:
            while True:
                envelope = await bus_queue.get()
                if "agent_activity" in topic:
                    evt = envelope.get("data", {}).get("event_type", "")
                    logger.info("ws_forwarding_agent_event", topic=topic, event_type=evt)
                try:
                    send_queue.put_nowait(envelope)
                except asyncio.QueueFull:
                    logger.warning("ws_send_queue_full", user_id=user_id, topic=topic)
        except asyncio.CancelledError:
            pass

    async def _receiver() -> None:
        """Read client messages and handle subscribe/unsubscribe/ping."""
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                action = msg.get("action")
                topic = msg.get("topic", "")

                if action == "subscribe" and topic:
                    if not may_subscribe(topic, who):
                        await websocket.send_json({"error": "forbidden", "topic": topic})
                        continue

                    if topic not in subscriptions:
                        bus_queue = subscribe(topic)
                        task = asyncio.create_task(
                            _topic_reader(topic, bus_queue),
                            name=f"ws-reader-{topic}",
                        )
                        subscriptions[topic] = (bus_queue, task)
                        # Subscription logged at trace level only (too verbose for debug)

                elif action == "unsubscribe" and topic:
                    sub = subscriptions.pop(topic, None)
                    if sub:
                        bus_queue, task = sub
                        task.cancel()
                        unsubscribe(topic, bus_queue)
                        logger.debug("ws_unsubscribed", user_id=user_id, topic=topic)

                elif action == "ping":
                    await websocket.send_json({"type": "pong"})

        except (WebSocketDisconnect, asyncio.CancelledError):
            pass

    # ── Main loop: run sender + receiver concurrently ─────
    sender_task: asyncio.Task[None] | None = None
    receiver_task: asyncio.Task[None] | None = None
    try:
        receiver_task = asyncio.create_task(_receiver(), name="ws-receiver")
        # Sender runs in a loop so it resumes after heartbeat timeouts
        sender_task = asyncio.create_task(_sender_loop(websocket, send_queue), name="ws-sender")
        # Wait for either to finish (typically receiver on disconnect)
        done, _ = await asyncio.wait(
            {receiver_task, sender_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        # If receiver finished (client disconnected), cancel sender
        for task in done:
            if task.exception():
                logger.warning("ws_task_error", error=str(task.exception()))
    finally:
        # ── Cleanup ───────────────────────────────────────
        if sender_task and not sender_task.done():
            sender_task.cancel()
        if receiver_task and not receiver_task.done():
            receiver_task.cancel()
        for topic, (bus_queue, task) in subscriptions.items():
            task.cancel()
            unsubscribe(topic, bus_queue)
        subscriptions.clear()
        logger.info("ws_disconnected", user_id=user_id)


async def _sender_loop(
    websocket: WebSocket,
    send_queue: asyncio.Queue[dict[str, Any]],
) -> None:
    """Continuously drain *send_queue* to the WebSocket, sending heartbeats on idle."""
    try:
        while True:
            try:
                hb = settings.ws.heartbeat_interval
                msg = await asyncio.wait_for(send_queue.get(), timeout=hb)
                await websocket.send_json(msg)
            except TimeoutError:
                await websocket.send_json({"type": "pong"})
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
