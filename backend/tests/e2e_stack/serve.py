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

"""Run the API for the Playwright suite with every external service faked.

Started by ``e2e/stack/run.ts`` (``python -m tests.e2e_stack.serve``), never in
production. Before uvicorn serves a request it installs the fakes the
integration tests use (they patch module attributes, so importing the app
first is safe), see :mod:`.fakes`:

* the network guard: no DNS or connect outside loopback, no connect to a
  developer's own stack on its default ports, no real ``claude``, ``codex``
  or ``copilot`` spawn;
* a fake embedder instead of the downloaded model;
* a fake ``claude`` CLI that answers every agent run with a short reply.

It also tags each request with the browser test it serves (``x-e2e-test``)
and mounts the ``/__e2e`` routes: seeding, reset and the guard report.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import uvicorn

from app.main import app
from tests.e2e_stack.attribution import ContextThreadPool, TestIdMiddleware
from tests.e2e_stack.fakes import TaggingClaudeRunner, TaggingGuard
from tests.e2e_stack.routes_delivery import router as delivery_router
from tests.e2e_stack.routes_seed import router as seed_router
from tests.e2e_stack.routes_stack import router as stack_router
from tests.e2e_stack.state import STATE
from tests.fakes.embeddings import FakeEmbedder


def _port(url: str) -> int:
    port = urlsplit(url.replace("+asyncpg", "")).port
    if port is None:
        raise SystemExit(f"e2e stack: {url!r} needs an explicit port")
    return port


def install_fakes(backend_port: int, log_path: Path) -> None:
    """Patch the process for the whole server run (never undone)."""
    patch = pytest.MonkeyPatch()
    guard = TaggingGuard(STATE.refusals, log_path)
    for name in ("DATABASE_URL", "REDIS_URL", "COLYSEUS_URL"):
        guard.allow_port(_port(os.environ[name]))
    guard.allow_port(backend_port)
    guard.install(patch)
    FakeEmbedder().install(patch)
    # Installed after the guard, so every other program still goes through it.
    TaggingClaudeRunner(f"http://127.0.0.1:{backend_port}", STATE.agent_problems).install(patch)


async def _serve(port: int) -> None:
    loop = asyncio.get_running_loop()
    # The stdlib loop, from asyncio.run, never uvloop: uvloop resolves and
    # connects in native code, past the patched ``socket`` functions, which
    # would leave the guard watching nothing. Fail rather than run blind.
    if not type(loop).__module__.startswith("asyncio"):
        raise SystemExit(f"e2e stack: needs the asyncio event loop, got {type(loop)!r}")
    loop.set_default_executor(ContextThreadPool())
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    await uvicorn.Server(config).serve()


def main() -> None:
    """Install the fakes, add the e2e routes and serve on loopback."""
    port = int(os.environ["E2E_BACKEND_PORT"])
    install_fakes(port, Path(os.environ["E2E_GUARD_LOG"]))
    app.add_middleware(TestIdMiddleware)
    app.include_router(seed_router)
    app.include_router(delivery_router)
    app.include_router(stack_router)
    asyncio.run(_serve(port))


if __name__ == "__main__":
    main()
