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

"""FakeClaudeRunner failure modes, and the checks that keep the fake honest."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.routing import Route

from app.mcp.bridge_env import BACKEND_URL_ENV, MCP_TOKEN_ENV
from app.services.claude_errors import ClaudeErrorCode
from app.services.claude_runner import ClaudeRunnerConfig, MCPServerConfig, run_claude_code
from tests.fakes.claude_contract import contract_problems, parse_argv
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import INSIGHT_BLOCK, AgentScript, ToolCall

ONE_SECOND = ClaudeRunnerConfig(timeout_seconds=1)


@pytest.mark.parametrize("streaming", [False, True])
async def test_hanging_agent_is_ended_only_by_the_runners_deadline(
    fake_claude: FakeClaudeRunner, tmp_path: Path, streaming: bool
) -> None:
    fake_claude.enqueue(AgentScript.timeout())
    callback = (lambda *_: None) if streaming else None
    started = time.monotonic()

    result = await run_claude_code("p", tmp_path, ONE_SECOND, callback)

    assert time.monotonic() - started >= 0.9
    assert result.success is False
    assert result.error_code is ClaudeErrorCode.TIMEOUT
    assert "1 seconds" in (result.error or "")
    assert fake_claude.runs[0].killed is True


@pytest.mark.parametrize("streaming", [False, True])
async def test_non_zero_exit_surfaces_stderr(
    fake_claude: FakeClaudeRunner, tmp_path: Path, streaming: bool
) -> None:
    fake_claude.enqueue(AgentScript.crash(exit_code=2, stderr="auth failed"))
    callback = (lambda *_: None) if streaming else None

    result = await run_claude_code("p", tmp_path, ClaudeRunnerConfig(), callback)

    assert result.success is False
    assert result.error_code is ClaudeErrorCode.UNKNOWN
    assert "exit code 2" in (result.error or "")
    assert "auth failed" in (result.error or "")


async def test_malformed_json_is_returned_raw_as_success(
    fake_claude: FakeClaudeRunner, tmp_path: Path
) -> None:
    fake_claude.enqueue(AgentScript.malformed("half a json {"))

    result = await run_claude_code("p", tmp_path, ClaudeRunnerConfig())

    assert (result.success, result.output) == (True, "half a json {")


async def test_max_turns_maps_to_its_code(fake_claude: FakeClaudeRunner, tmp_path: Path) -> None:
    fake_claude.enqueue(AgentScript.max_turns())

    result = await run_claude_code("p", tmp_path, ClaudeRunnerConfig())

    assert result.success is False
    assert result.error_code is ClaudeErrorCode.MAX_TURNS


async def test_insight_and_preamble_reach_the_caller_untouched(
    fake_claude: FakeClaudeRunner, tmp_path: Path
) -> None:
    fake_claude.enqueue(AgentScript.ok("# Doc").with_preamble().with_insight())

    result = await run_claude_code("p", tmp_path, ClaudeRunnerConfig())

    assert result.output.startswith(INSIGHT_BLOCK)
    assert result.output.endswith("# Doc")


async def test_unscripted_runs_are_recorded_and_fail_closed(tmp_path: Path) -> None:
    runner = FakeClaudeRunner()

    process = await runner.spawn(["claude", "-p", "hello"], {"cwd": str(tmp_path), "env": {}})

    assert await process.wait() == 1
    assert runner.unscripted[0].prompt == "hello"
    with pytest.raises(pytest.fail.Exception, match="unscripted"):
        runner.assert_all_scripted()


async def test_a_crashing_mcp_route_is_a_500_and_fails_the_test(tmp_path: Path) -> None:
    async def boom(_: Any) -> Any:
        raise RuntimeError("handler bug")

    app = Starlette(routes=[Route("/mcp/tools/{name}", boom, methods=["POST"])])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://mcp") as client:
        runner = FakeClaudeRunner(client)
        runner.enqueue(AgentScript.ok("x", ToolCall("write_bud", {"bud_number": 1})))
        config = ClaudeRunnerConfig(mcp=MCPServerConfig("http://backend", "tok"))
        argv = ["claude", "-p", "p", "--mcp-config", _write_mcp_config(tmp_path, config)]

        await runner.spawn(argv, {"env": {}})

    (call,) = runner.tool_calls()
    assert (call.status_code, call.response) == (500, {"error": "Backend returned HTTP 500"})
    with pytest.raises(pytest.fail.Exception, match="MCP route crashed"):
        runner.assert_all_scripted()


def _write_mcp_config(tmp_path: Path, config: ClaudeRunnerConfig) -> str:
    assert config.mcp is not None
    env = {
        BACKEND_URL_ENV: config.mcp.backend_url,
        MCP_TOKEN_ENV: config.mcp.mcp_token,
    }
    path = tmp_path / "mcp.json"
    server = {"command": "/bin/sh", "args": [__file__], "env": env}
    path.write_text('{"mcpServers": {"bodhiorchard": ' + json.dumps(server) + "}}")
    return str(path)


def test_stream_json_without_verbose_breaks_the_contract() -> None:
    run = parse_argv(["claude", "-p", "x", "--output-format", "stream-json"], None, {})

    assert contract_problems(run) == ["--output-format stream-json requires --verbose"]


async def test_the_real_runner_meets_the_cli_contract(
    fake_claude: FakeClaudeRunner, tmp_path: Path
) -> None:
    fake_claude.enqueue(AgentScript.ok())
    config = ClaudeRunnerConfig(mcp=MCPServerConfig("http://backend", "tok"))

    await run_claude_code("p", tmp_path, config, progress_callback=lambda *_: None)

    assert contract_problems(fake_claude.runs[0]) == []
    assert fake_claude.runs[0].mcp_backend_url == "http://backend"


async def test_server_wide_allow_rule_lets_every_bodhiorchard_tool_through(
    fake_claude: FakeClaudeRunner, tmp_path: Path
) -> None:
    fake_claude.enqueue(AgentScript.ok("x", ToolCall("get_features", {"query": "a"})))
    config = ClaudeRunnerConfig(
        mcp=MCPServerConfig("http://backend", "tok"), allowed_tools=["mcp__bodhiorchard"]
    )
    fake_claude.mcp_client = None

    await run_claude_code("p", tmp_path, config)

    (call,) = fake_claude.tool_calls()
    assert call.response == {"error": "no client"}
    fake_claude.problems.clear()
