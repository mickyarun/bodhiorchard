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

"""FakeClaudeRunner driven through the real ``run_claude_code``.

The runner builds the real command line and parses the fake's output, so
these tests pin both the fake's fidelity and the runner's handling of each
CLI outcome.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Header
from httpx import ASGITransport, AsyncClient

from app.services.claude_errors import ClaudeErrorCode
from app.services.claude_runner import ClaudeRunnerConfig, MCPServerConfig, run_claude_code
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import INSIGHT_BLOCK, AgentScript, Say, ToolCall


@pytest.fixture
async def echo_mcp(fake_claude: FakeClaudeRunner) -> AsyncIterator[list[dict[str, Any]]]:
    """A stand-in MCP route that echoes params and refuses a bad token."""
    seen: list[dict[str, Any]] = []
    app = FastAPI()

    @app.post("/mcp/tools/{name}")
    async def call(name: str, body: dict[str, Any], authorization: str = Header()) -> Any:
        seen.append({"name": name, "auth": authorization, **body})
        if name == "broken_tool":
            return {"error": "bad params"}
        return {"ok": True, "echo": body["params"]}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://mcp") as client:
        fake_claude.mcp_client = client
        yield seen


def _mcp_config(tools: list[str] | None = None) -> ClaudeRunnerConfig:
    mcp = MCPServerConfig("http://backend", "tok-123", tool_names=tools or [])
    return ClaudeRunnerConfig(timeout_seconds=5, mcp=mcp)


async def test_json_success_reports_result_cost_and_command_line(
    fake_claude: FakeClaudeRunner, tmp_path: Path
) -> None:
    fake_claude.enqueue(AgentScript.ok("# Spec\n\nBody"))
    config = ClaudeRunnerConfig(model="claude-sonnet-4-5", max_turns=7, timeout_seconds=5)

    result = await run_claude_code("write the spec", tmp_path, config)

    assert result.success is True
    assert result.output == "# Spec\n\nBody"
    assert result.cost_usd == pytest.approx(0.0123)
    assert result.turns_used == 3
    run = fake_claude.runs[0]
    assert run.prompt == "write the spec"
    assert run.flag("--model") == "claude-sonnet-4-5"
    assert run.flag("--max-turns") == "7"
    assert run.flag("--add-dir") == str(tmp_path.resolve())
    assert run.mcp_token is None


async def test_tool_calls_reach_mcp_with_the_runs_token_and_stream_progress(
    fake_claude: FakeClaudeRunner, echo_mcp: list[dict[str, Any]], tmp_path: Path
) -> None:
    script = AgentScript.ok(
        "done",
        Say("Looking at the code first."),
        ToolCall("write_feature", {"name": "Orders"}),
        ToolCall("broken_tool", lambda run: {"prompt_len": len(run.prompt)}),
    )
    fake_claude.when("synthesise", script)
    seen_tools: list[str] = []

    result = await run_claude_code(
        "synthesise features",
        tmp_path,
        _mcp_config(),
        progress_callback=lambda name, _input: seen_tools.append(name),
    )

    assert result.success is True
    assert [c["name"] for c in echo_mcp] == ["write_feature", "broken_tool"]
    assert {c["auth"] for c in echo_mcp} == {"Bearer tok-123"}
    assert echo_mcp[1]["params"] == {"prompt_len": len("synthesise features")}
    assert seen_tools == ["mcp__bodhiorchard__write_feature", "mcp__bodhiorchard__broken_tool"]
    calls = fake_claude.tool_calls()
    assert [c.is_error for c in calls] == [False, True]
    assert fake_claude.runs[0].output_format == "stream-json"


async def test_tool_outside_the_exposed_list_is_refused_without_a_request(
    fake_claude: FakeClaudeRunner, echo_mcp: list[dict[str, Any]], tmp_path: Path
) -> None:
    fake_claude.enqueue(AgentScript.ok("x", ToolCall("write_bud", {"body": "#"})))

    await run_claude_code("p", tmp_path, _mcp_config(tools=["get_bud_context"]))

    assert echo_mcp == []
    (call,) = fake_claude.tool_calls()
    assert call.refused is True
    assert call.is_error is True


async def test_timeout_kills_the_process_and_maps_to_timeout_code(
    fake_claude: FakeClaudeRunner, tmp_path: Path
) -> None:
    fake_claude.enqueue(AgentScript.timeout())

    result = await run_claude_code("p", tmp_path, ClaudeRunnerConfig(timeout_seconds=9))

    assert result.success is False
    assert result.error_code is ClaudeErrorCode.TIMEOUT
    assert "9 seconds" in (result.error or "")
    assert fake_claude.runs[0].killed is True


async def test_streaming_timeout_also_kills_and_maps(
    fake_claude: FakeClaudeRunner, tmp_path: Path
) -> None:
    fake_claude.enqueue(AgentScript.timeout())

    result = await run_claude_code(
        "p", tmp_path, ClaudeRunnerConfig(timeout_seconds=4), progress_callback=lambda *_: None
    )

    assert result.error_code is ClaudeErrorCode.TIMEOUT
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

    assert result.success is True
    assert result.output == "half a json {"


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


async def test_env_handed_to_the_cli_is_filtered(
    fake_claude: FakeClaudeRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
    monkeypatch.setenv("ENCRYPTION_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    fake_claude.enqueue(AgentScript.ok())

    await run_claude_code("p", tmp_path, ClaudeRunnerConfig(env_extra={"BUD_ID": "7"}))

    env = fake_claude.runs[0].env
    assert "DATABASE_URL" not in env
    assert "ENCRYPTION_KEY" not in env
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-test"
    assert env["BUD_ID"] == "7"


async def test_unscripted_runs_are_recorded_and_fail_closed(tmp_path: Path) -> None:
    runner = FakeClaudeRunner()

    process = await runner.spawn(["claude", "-p", "hello"], {"cwd": str(tmp_path), "env": {}})

    assert await process.wait() == 1
    assert runner.unscripted[0].prompt == "hello"
    with pytest.raises(pytest.fail.Exception):
        runner.assert_all_scripted()
