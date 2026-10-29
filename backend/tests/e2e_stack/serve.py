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
first is safe):

* :class:`ExternalCallGuard`: no DNS or connect outside loopback, no connect
  to a developer's own stack on its default ports, no real ``claude``,
  ``codex`` or ``copilot`` spawn;
* :class:`FakeEmbedder`: hashed vectors instead of the downloaded model;
* :class:`FakeClaudeRunner`: every agent run answers from a harmless script.

Every refusal is appended to ``E2E_GUARD_LOG`` and listed by
``GET /__e2e/guard``, which the suite checks after each test.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest
import uvicorn

from app.main import app
from tests.e2e_stack.routes import router
from tests.e2e_stack.state import STATE
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript
from tests.fakes.embeddings import FakeEmbedder
from tests.fakes.guard import OLLAMA_PORT, ExternalCallBlockedError, ExternalCallGuard, is_loopback

# Default ports of a developer's own stack (Postgres, Redis, backend, frontend,
# Vite's default, multiplayer, Ollama). The e2e stack never uses them.
DEV_STACK_PORTS = frozenset({5432, 6379, 8000, 3000, 5173, 2567, 11434})


class LoggingGuard(ExternalCallGuard):
    """An :class:`ExternalCallGuard` that also appends each refusal to a file.

    One refusal is expected rather than a violation: the AI settings and the
    setup wizard probe a local Ollama on its default port by design. The
    probe is still refused (so it reads as "not installed" and never
    reaches a developer's own Ollama), just not counted.
    """

    def __init__(self, log_path: Path) -> None:
        super().__init__()
        self.log_path = log_path
        self.blocked_ports |= DEV_STACK_PORTS

    def check_address(self, family: int, address: Any) -> None:
        if isinstance(address, tuple) and len(address) >= 2:
            host, port = str(address[0]), int(address[1])
            if port == OLLAMA_PORT and is_loopback(host):
                raise ExternalCallBlockedError("blocked by ExternalCallGuard: local Ollama probe")
        super().check_address(family, address)

    def _refuse(self, what: str) -> ExternalCallBlockedError:
        error = super()._refuse(what)
        with self.log_path.open("a", encoding="utf-8") as log:
            log.write(what + "\n")
        return error


def _port(url: str) -> int:
    port = urlsplit(url.replace("+asyncpg", "")).port
    if port is None:
        raise SystemExit(f"e2e stack: {url!r} needs an explicit port")
    return port


def install_fakes(backend_port: int, log_path: Path) -> None:
    """Patch the process for the whole server run (never undone)."""
    patch = pytest.MonkeyPatch()
    guard = LoggingGuard(log_path)
    for name in ("DATABASE_URL", "REDIS_URL", "COLYSEUS_URL"):
        guard.allow_port(_port(os.environ[name]))
    guard.allow_port(backend_port)
    guard.install(patch)

    embedder = FakeEmbedder()
    embedder.install(patch)

    claude = FakeClaudeRunner(httpx.AsyncClient(base_url=f"http://127.0.0.1:{backend_port}"))
    claude.default = AgentScript.ok("Done.")
    claude.install(patch)

    STATE.guard = guard
    STATE.claude = claude


def main() -> None:
    """Install the fakes, add the seeding routes and serve on loopback."""
    port = int(os.environ["E2E_BACKEND_PORT"])
    install_fakes(port, Path(os.environ["E2E_GUARD_LOG"]))
    app.include_router(router)
    # loop="asyncio", never uvloop: uvloop resolves and connects in native
    # code, past the patched ``socket`` functions, which would leave the
    # guard watching nothing.
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", workers=1, loop="asyncio")


if __name__ == "__main__":
    main()
