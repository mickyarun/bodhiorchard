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

"""Tests for the event_bus transport registration + fanout."""

from __future__ import annotations

import asyncio

import pytest

from app.services import event_bus


@pytest.fixture(autouse=True)
def _reset_event_bus() -> None:
    """Clear transports and subscribers between tests — module-level state."""
    event_bus.clear_transports()
    event_bus._subscribers.clear()
    event_bus._transport_tasks.clear()
    yield
    event_bus.clear_transports()
    event_bus._subscribers.clear()
    event_bus._transport_tasks.clear()


async def test_transport_invoked_on_publish() -> None:
    calls: list[tuple[str, dict]] = []

    async def fake(topic: str, payload: dict) -> None:
        calls.append((topic, payload))

    event_bus.register_transport(fake)
    event_bus.publish("agent_activity:abc", {"x": 1})

    # Transports run as detached tasks — let the loop drain them.
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert calls == [("agent_activity:abc", {"x": 1})]


async def test_register_transport_is_idempotent() -> None:
    calls = 0

    async def fake(_topic: str, _payload: dict) -> None:
        nonlocal calls
        calls += 1

    event_bus.register_transport(fake)
    event_bus.register_transport(fake)  # duplicate — should be ignored
    event_bus.publish("t", {})
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert calls == 1


async def test_transport_exception_does_not_kill_siblings() -> None:
    survivor_called = False

    async def broken(_topic: str, _payload: dict) -> None:
        raise RuntimeError("boom")

    async def survivor(_topic: str, _payload: dict) -> None:
        nonlocal survivor_called
        survivor_called = True

    event_bus.register_transport(broken)
    event_bus.register_transport(survivor)
    event_bus.publish("t", {})
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert survivor_called


async def test_transport_runs_even_without_queue_subscribers() -> None:
    """Zero queue subscribers must not skip transport fanout."""
    called = False

    async def fake(_topic: str, _payload: dict) -> None:
        nonlocal called
        called = True

    event_bus.register_transport(fake)
    event_bus.publish("lonely_topic", {})
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert called


async def test_queue_subscribers_still_receive_when_transports_present() -> None:
    """Transport fanout must not interfere with queue fanout."""

    async def noop(_topic: str, _payload: dict) -> None:
        return

    event_bus.register_transport(noop)
    queue = event_bus.subscribe("t")
    event_bus.publish("t", {"hi": 1})

    envelope = queue.get_nowait()
    assert envelope == {"topic": "t", "data": {"hi": 1}}


async def test_transport_task_set_drains_after_completion() -> None:
    async def fake(_topic: str, _payload: dict) -> None:
        return

    event_bus.register_transport(fake)
    event_bus.publish("t", {})
    # Let detached task run + done-callback fire.
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert len(event_bus._transport_tasks) == 0
