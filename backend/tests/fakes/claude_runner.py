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

1. records the invocation as an :class:`AgentRun`;
2. picks the :class:`AgentScript` for it (first matching rule, else the
   next queued script, else the default);
3. executes the script's MCP tool calls **for real** by POSTing to the app's
   ``/mcp/tools/{name}`` route with the token from the run's MCP config,
   exactly as the stdio bridge does;
4. returns a :class:`FakeProcess` that replays CLI-shaped stdout, so the
   runner's parsing, error mapping and progress callbacks run unchanged.

Any other program (``git``) is passed through to the real spawn.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.services import claude_runner
from tests.fakes.claude_process import MCP_PREFIX, FakeProcess
from tests.fakes.claude_script import AgentRun, AgentScript, ToolCall, ToolCallRecord
from tests.fakes.guard import binary_name

Matcher = Callable[[AgentRun], bool]


def _parse_argv(argv: list[str], cwd: str | None, env: dict[str, str]) -> AgentRun:
    run = AgentRun(argv=argv, prompt="", cwd=cwd, env=env, output_format="json")
    run.prompt = run.flag("-p") or ""
    run.output_format = run.flag("--output-format") or "json"
    allowed = run.flag("--allowedTools")
    run.allowed_tools = allowed.split(",") if allowed else []
    config_path = run.flag("--mcp-config")
    if config_path:
        server = json.loads(Path(config_path).read_text())["mcpServers"]["bodhiorchard"]
        server_env = server["env"]
        run.mcp_backend_url = server_env["BODHIORCHARD_BACKEND_URL"]
        run.mcp_token = server_env["BODHIORCHARD_MCP_TOKEN"]
        tools = server_env.get("BODHIORCHARD_MCP_TOOLS", "")
        run.mcp_tools = [t for t in tools.split(",") if t]
    return run


class FakeClaudeRunner:
    """Answers ``claude`` spawns from scripts; see the module docstring."""

    def __init__(self, mcp_client: httpx.AsyncClient | None = None) -> None:
        self.mcp_client = mcp_client
        self.runs: list[AgentRun] = []
        self.unscripted: list[AgentRun] = []
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
        params = call.resolve(run)
        exposed = not run.mcp_tools or call.name in run.mcp_tools
        allowed = not run.allowed_tools or MCP_PREFIX + call.name in run.allowed_tools
        if run.mcp_token is None or not exposed or not allowed:
            reason = "no MCP server configured" if run.mcp_token is None else "tool not exposed"
            return ToolCallRecord(call.name, params, None, {"error": reason}, refused=True)
        if self.mcp_client is None:
            raise AssertionError("FakeClaudeRunner.mcp_client is not set; cannot run MCP tools")
        response = await self.mcp_client.post(
            f"/mcp/tools/{call.name}",
            json={"params": params},
            headers={"Authorization": f"Bearer {run.mcp_token}"},
        )
        try:
            body: Any = response.json()
        except ValueError:
            body = response.text
        return ToolCallRecord(call.name, params, response.status_code, body)

    async def spawn(self, argv: list[str], kwargs: dict[str, Any]) -> FakeProcess:
        """Run the script for one ``claude`` spawn and hand back a process."""
        env = dict(kwargs.get("env") or {})
        run = _parse_argv(argv, kwargs.get("cwd"), env)
        self.runs.append(run)
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
        """Fail when a run had no script (the test missed an agent call)."""
        if self.unscripted:
            prompts = [run.prompt[:120] for run in self.unscripted]
            pytest.fail(f"unscripted agent runs: {prompts}", pytrace=False)
