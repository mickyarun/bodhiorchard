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

"""The integration-test fakes, adapted to run for a whole server's lifetime.

Every refusal and every agent-run problem is tagged with the browser test
that caused it (see :mod:`.attribution`), so a failing test is the one that
did it, not whichever test happened to check next.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from tests.e2e_stack.attribution import TaggedLog, TaggingList, current_test
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentRun, AgentScript
from tests.fakes.guard import OLLAMA_PORT, ExternalCallBlockedError, ExternalCallGuard, is_loopback

# Default ports of a developer's own stack (Postgres, Redis, backend, frontend,
# Vite's default, multiplayer, Ollama). The e2e stack never uses them.
DEV_STACK_PORTS = frozenset({5432, 6379, 8000, 3000, 5173, 2567, 11434})


class TaggingGuard(ExternalCallGuard):
    """An :class:`ExternalCallGuard` that tags each refusal and appends it to a file.

    One refusal is expected rather than a violation: the AI settings and the
    setup wizard probe a local Ollama on its default port by design. The
    probe is still refused (so it reads as "not installed" and never
    reaches a developer's own Ollama), just not counted.
    """

    def __init__(self, log: TaggedLog, log_path: Path) -> None:
        super().__init__()
        self.log = log
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
        self.log.add(what)
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(f"[{current_test.get() or 'no test'}] {what}\n")
        return error


def _unscripted(run: AgentRun) -> str:
    return f"unscripted agent run: {run.prompt[:120]!r}"


class TaggingClaudeRunner(FakeClaudeRunner):
    """A :class:`FakeClaudeRunner` whose problems are tagged as they happen.

    Every run gets a short successful reply unless a script says otherwise.
    """

    def __init__(self, backend_url: str, log: TaggedLog) -> None:
        super().__init__(httpx.AsyncClient(base_url=backend_url))
        self.default = AgentScript.ok("Done.")
        self.problems = TaggingList(log, str)
        self.unscripted = TaggingList(log, _unscripted)
