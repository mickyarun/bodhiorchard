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

"""Scripted stand-in for the ``claude`` CLI, faked at the subprocess layer.

Every agent run in the app ends in ``claude_runner.run_claude_code``, which
builds the real command line (prompt, ``--mcp-config``, ``--allowedTools``,
the filtered env) and spawns it with ``asyncio.create_subprocess_exec``.
:class:`FakeClaudeRunner` intercepts that spawn when ``argv[0]`` is
``claude`` and, instead of a process:

1. records the invocation as an :class:`AgentRun` and checks the parts of
   the command line the real CLI would reject (see :mod:`.claude_contract`);
2. picks the :class:`AgentScript` for it (first matching rule, else the
   next queued script, else the default);
3. executes the script's MCP tool calls **for real** by POSTing to the app's
   ``/mcp/tools/{name}`` route with the token from the run's MCP config,
   exactly as the stdio bridge does (a crash in the route is recorded as a
   500, the way the bridge reports it);
4. returns a :class:`FakeProcess` that replays CLI-shaped stdout, so the
   runner's parsing, error mapping and progress callbacks run unchanged.

All tool calls run at spawn time, before the runner reads any output. Any
other program (``git``) is passed through to the real spawn.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.services import claude_runner
from tests.fakes.claude_contract import contract_problems, parse_argv, tool_allowed
from tests.fakes.claude_process import FakeProcess
from tests.fakes.claude_script import AgentRun, AgentScript, ToolCall, ToolCallRecord
from tests.fakes.guard import binary_name

Matcher = Callable[[AgentRun], bool]
VERSION_SCRIPT = AgentScript.malformed("2.0.0 (Claude Code)")


class FakeClaudeRunner:
    """Answers ``claude`` spawns from scripts; see the module docstring."""

    def __init__(self, mcp_client: httpx.AsyncClient | None = None) -> None:
        self.mcp_client = mcp_client
        self.runs: list[AgentRun] = []
        self.unscripted: list[AgentRun] = []
        self.problems: list[str] = []
        self.default: AgentScript | None = None
        self._rules: list[tuple[Matcher, AgentScript]] = []
        self._queue: deque[AgentScript] = deque()

    # ── scripting ─────────────────────────────────────────────────
    def when(self, matcher: Matcher | str, script: AgentScript) -> None:
        """Use ``script`` for every run whose prompt matches.

        A string matches when it appears in the prompt; a callable gets the
        :class:`AgentRun` (prompt, flags, env, MCP config).
        """
        if isinstance(matcher, str):
            needle = matcher
            self._rules.append((lambda run: needle in run.prompt, script))
        else:
            self._rules.append((matcher, script))

    def enqueue(self, *scripts: AgentScript) -> None:
        """Use these scripts, in order, for runs no rule matched."""
        self._queue.extend(scripts)

    def _pick(self, run: AgentRun) -> AgentScript | None:
        for matcher, script in self._rules:
            if matcher(run):
                return script
        if self._queue:
            return self._queue.popleft()
        return self.default

    # ── execution ─────────────────────────────────────────────────
    async def _call_tool(self, run: AgentRun, call: ToolCall) -> ToolCallRecord:
        try:
            params = call.resolve(run)
        except Exception as exc:  # noqa: BLE001 — a broken script must fail the test
            self.problems.append(f"params for {call.name!r} raised {exc!r}")
            return ToolCallRecord(call.name, {}, None, {"error": "bad script"}, refused=True)
        if run.mcp_token is None or not tool_allowed(run, call.name):
            reason = "no MCP server configured" if run.mcp_token is None else "tool not exposed"
            return ToolCallRecord(call.name, params, None, {"error": reason}, refused=True)
        if self.mcp_client is None:
            self.problems.append("FakeClaudeRunner.mcp_client is not set; cannot run MCP tools")
            return ToolCallRecord(call.name, params, None, {"error": "no client"}, refused=True)
        try:
            response = await self.mcp_client.post(
                f"/mcp/tools/{call.name}",
                json={"params": params},
                headers={"Authorization": f"Bearer {run.mcp_token}"},
            )
        except Exception as exc:  # noqa: BLE001 — the bridge reports a crash as HTTP 500
            self.problems.append(f"MCP route crashed on {call.name!r}: {exc!r}")
            return ToolCallRecord(call.name, params, 500, {"error": "Backend returned HTTP 500"})
        try:
            body: Any = response.json()
        except ValueError:
            body = response.text
        return ToolCallRecord(call.name, params, response.status_code, body)

    async def spawn(self, argv: list[str], kwargs: dict[str, Any]) -> FakeProcess:
        """Run the script for one ``claude`` spawn and hand back a process."""
        env = dict(kwargs.get("env") or {})
        run = parse_argv(argv, kwargs.get("cwd"), env)
        if "--version" in argv:
            return FakeProcess(run, VERSION_SCRIPT)
        self.runs.append(run)
        self.problems.extend(contract_problems(run))
        script = self._pick(run)
        if script is None:
            self.unscripted.append(run)
            script = AgentScript.crash(stderr="FakeClaudeRunner: no script for this run")
        run.script = script
        for step in script.steps:
            if isinstance(step, ToolCall):
                run.tool_calls.append(await self._call_tool(run, step))
        return FakeProcess(run, script)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Intercept ``claude`` spawns; everything else goes to the real spawn."""
        passthrough = asyncio.create_subprocess_exec
        fake = self

        async def spawn(program: Any, *args: Any, **kwargs: Any) -> Any:
            if binary_name(program) == "claude":
                return await fake.spawn([str(program), *map(str, args)], kwargs)
            return await passthrough(program, *args, **kwargs)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        monkeypatch.setattr(claude_runner, "is_claude_cli_available", lambda: True)

    # ── assertions ────────────────────────────────────────────────
    def tool_calls(self, tool: str | None = None) -> list[ToolCallRecord]:
        """Every tool call across all runs, optionally only to ``tool``."""
        calls = [call for run in self.runs for call in run.tool_calls]
        return [c for c in calls if tool is None or c.name == tool]

    def assert_all_scripted(self) -> None:
        """Fail on unscripted runs, broken scripts, crashes and CLI contract breaks."""
        failures = [f"unscripted agent run: {run.prompt[:120]!r}" for run in self.unscripted]
        failures.extend(self.problems)
        if failures:
            pytest.fail("FakeClaudeRunner:\n  - " + "\n  - ".join(failures), pytrace=False)
