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

"""Point the app's process-wide state at test doubles for one test.

Background work (scan fanout, MCP audit rows, job handlers) opens its own
``AsyncSessionLocal()`` instead of using the request session. Each module
imported that name directly, so :func:`bind_app_sessions` rebinds it in
every loaded ``app.*`` module. :func:`disable_redis` makes ``get_redis()``
answer ``None`` (every caller fails open), and :class:`EventRecorder`
captures ``event_bus.publish`` traffic through the bus's own transport hook.
"""

from __future__ import annotations

import asyncio
import importlib
import pkgutil
import sys
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app
from app import database
from app.config import settings
from app.services import event_bus, redis_client

_ENTRYPOINTS = ("app.scripts", "app.main", "app.mcp.stdio_bridge")


@cache
def import_app_modules() -> int:
    """Import every ``app.*`` module once, so none binds the real factory later.

    Several modules import collaborators inside functions; without this a
    module first imported mid-test would still hold the dev-database
    ``AsyncSessionLocal``. Entry points are skipped: ``app.scripts`` (one-off
    CLIs), ``app.main`` (configures logging at import) and the MCP stdio bridge.
    """
    count = 0
    for info in pkgutil.walk_packages(app.__path__, "app."):
        if info.name.startswith(_ENTRYPOINTS):
            continue
        importlib.import_module(info.name)
        count += 1
    return count


def bind_app_sessions(
    monkeypatch: pytest.MonkeyPatch, factory: async_sessionmaker[AsyncSession]
) -> int:
    """Rebind ``AsyncSessionLocal`` in every app module; return the count."""
    import_app_modules()
    original = database.AsyncSessionLocal
    bound = 0
    for name, module in list(sys.modules.items()):
        if name != "app" and not name.startswith("app."):
            continue
        if getattr(module, "AsyncSessionLocal", None) is original:
            monkeypatch.setattr(module, "AsyncSessionLocal", factory)
            bound += 1
    return bound


async def drain_tasks_started_since(before: set[asyncio.Task[Any]], timeout: float = 5.0) -> None:
    """Let tasks started after ``before`` finish (up to ``timeout``), then cancel the rest."""
    current = asyncio.current_task()
    started = [t for t in asyncio.all_tasks() - before if t is not current and not t.done()]
    if not started:
        return
    _, pending = await asyncio.wait(started, timeout=timeout)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


def disable_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``get_redis()`` return ``None`` so nothing reaches a real Redis."""
    monkeypatch.setattr(redis_client, "_redis", None)
    monkeypatch.setattr(redis_client, "_redis_available", False)


def isolate_data_dir(monkeypatch: pytest.MonkeyPatch, root: Path) -> Path:
    """Send clones, worktrees and uploads under ``root`` instead of the dev data dir."""
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings.storage, "data_dir", str(root))
    return root


@dataclass
class EventRecorder:
    """Every ``event_bus.publish(topic, data)`` made while installed."""

    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def _transport(self, topic: str, data: dict[str, Any]) -> None:
        self.events.append((topic, data))

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Replace the bus's transport list with this recorder only."""
        monkeypatch.setattr(event_bus, "_transports", [self._transport])

    def topics(self, prefix: str = "") -> list[str]:
        """Topics published so far that start with ``prefix``."""
        return [topic for topic, _ in self.events if topic.startswith(prefix)]

    def payloads(self, topic: str) -> list[dict[str, Any]]:
        """Payloads published on exactly ``topic``."""
        return [data for name, data in self.events if name == topic]

    async def settle(self) -> None:
        """Wait until every transport task the bus has started has finished."""
        await asyncio.sleep(0)
        pending = [task for task in event_bus._transport_tasks if not task.done()]
        if pending:
            await asyncio.wait(pending, timeout=5.0)
