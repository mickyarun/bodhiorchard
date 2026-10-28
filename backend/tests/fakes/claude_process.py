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

"""A stand-in for ``asyncio.subprocess.Process`` that replays scripted output.

The real ``claude_runner`` reads the CLI either all at once
(``communicate()``, ``--output-format json``) or line by line
(``stdout.readline()``, ``--output-format stream-json``). This process
serves the bytes :func:`render_stdout` produced for the script either way,
so the runner's own parsing, error mapping and progress callbacks run
unchanged.
"""

from __future__ import annotations

import asyncio
import io
import json
from typing import Any

from tests.fakes.claude_contract import MCP_PREFIX
from tests.fakes.claude_script import AgentRun, AgentScript, Say, ToolCallRecord


def _result_event(script: AgentScript) -> dict[str, Any]:
    return {
        "type": "result",
        "subtype": script.subtype,
        "is_error": script.subtype != "success",
        "result": script.result,
        "total_cost_usd": script.cost_usd,
        "num_turns": script.num_turns,
        "usage": {"cache_read_input_tokens": 100, "cache_creation_input_tokens": 10},
    }


def _stream_events(run: AgentRun, script: AgentScript) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [{"type": "system", "subtype": "init", "cwd": run.cwd}]
    calls = iter(run.tool_calls)
    for index, step in enumerate(script.steps):
        if isinstance(step, Say):
            content = [{"type": "text", "text": step.text}]
            events.append({"type": "assistant", "message": {"content": content}})
            continue
        call: ToolCallRecord = next(calls)
        tool_id = f"toolu_{index:04d}"
        use: dict[str, Any] = {
            "type": "tool_use",
            "id": tool_id,
            "name": MCP_PREFIX + call.name,
            "input": call.params,
        }
        events.append({"type": "assistant", "message": {"content": [use]}})
        result: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "is_error": call.is_error,
            "content": json.dumps(call.response, default=str),
        }
        events.append({"type": "user", "message": {"content": [result]}})
    if script.exit_code == 0:
        events.append(_result_event(script))
    return events


def render_stdout(run: AgentRun, script: AgentScript) -> bytes:
    """The bytes the real CLI would print for ``script`` in ``run``'s format."""
    if script.raw_stdout is not None:
        return script.raw_stdout.encode()
    if run.output_format == "stream-json":
        lines = [json.dumps(event, default=str) for event in _stream_events(run, script)]
        return ("\n".join(lines) + "\n").encode()
    if script.exit_code != 0:
        return b""
    return json.dumps(_result_event(script)).encode()


class FakeStream:
    """The subset of ``asyncio.StreamReader`` the runner uses."""

    def __init__(self, data: bytes, *, hang_until: asyncio.Event | None = None) -> None:
        self._buffer = io.BytesIO(data)
        self._hang_until = hang_until

    async def readline(self) -> bytes:
        """Next line; a hanging script blocks at the end until it is killed."""
        line = self._buffer.readline()
        if not line and self._hang_until is not None:
            await self._hang_until.wait()
        return line

    async def read(self, size: int = -1) -> bytes:
        """Up to ``size`` bytes (all remaining when negative)."""
        return self._buffer.read(size if size >= 0 else None)


class FakeProcess:
    """The subset of ``asyncio.subprocess.Process`` the runner uses."""

    _next_pid = 90_000

    def __init__(self, run: AgentRun, script: AgentScript) -> None:
        FakeProcess._next_pid += 1
        self.pid = FakeProcess._next_pid
        self._run = run
        self._script = script
        self._killed = asyncio.Event()
        stdout = render_stdout(run, script)
        hang = self._killed if script.times_out else None
        self.stdout = FakeStream(stdout, hang_until=hang)
        self.stderr = FakeStream(script.stderr.encode())
        self._stdout_bytes = stdout
        self.returncode: int | None = None

    async def communicate(self, stdin: bytes | None = None) -> tuple[bytes, bytes]:
        """All of stdout and stderr; a hanging script blocks until it is killed.

        Only the runner's own ``asyncio.wait_for`` deadline gets it unstuck, so
        a runner that lost its timeout would hang the test instead of passing.
        """
        if self._script.times_out:
            await self._killed.wait()
            return b"", b""
        self.returncode = self._script.exit_code
        return self._stdout_bytes, self._script.stderr.encode()

    async def wait(self) -> int:
        """Exit status (``-9`` once killed)."""
        if self.returncode is None:
            self.returncode = -9 if self._run.killed else self._script.exit_code
        return self.returncode

    def kill(self) -> None:
        """Record the kill the runner issues on timeout or cancellation."""
        self._run.killed = True
        self.returncode = -9
        self._killed.set()

    terminate = kill
