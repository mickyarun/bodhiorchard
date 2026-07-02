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

"""Unit tests for the Copilot adapter, MCP config builders, and registry."""

import json
import os
from unittest.mock import AsyncMock, patch

from app.models.organization import AIProvider, Organization
from app.services.ai_runner import copilot_provider as cp
from app.services.ai_runner.claude_provider import ClaudeProvider
from app.services.ai_runner.copilot_provider import CopilotProvider
from app.services.ai_runner.mcp_config import (
    SERVER_NAME,
    build_codex_mcp,
    build_copilot_mcp,
)
from app.services.ai_runner.registry import provider_for
from app.services.claude_runner import NO_REPO_CONTEXT, ClaudeRunnerConfig, MCPServerConfig

_SAMPLE_JSONL = "\n".join(
    [
        '{"type":"session.mcp_servers_loaded","data":{"servers":[]}}',
        '{"type":"assistant.message","data":{"content":"draft answer","model":"gpt-5-mini"}}',
        '{"type":"assistant.message","data":{"content":"FINAL ANSWER","model":"gpt-5-mini"}}',
        '{"type":"result","exitCode":0,"usage":{"premiumRequests":0}}',
    ]
)


def test_parse_output_takes_last_assistant_message() -> None:
    assert cp._parse_output(_SAMPLE_JSONL) == "FINAL ANSWER"


def test_parse_output_ignores_non_json_lines() -> None:
    assert cp._parse_output("garbage\n" + _SAMPLE_JSONL) == "FINAL ANSWER"


def test_parse_output_survives_null_data() -> None:
    """A version-drifted ``assistant.message`` with null ``data`` must not raise."""
    stream = '{"type":"assistant.message","data":null}\n' + _SAMPLE_JSONL
    assert cp._parse_output(stream) == "FINAL ANSWER"


def test_compose_prompt_prepends_files(tmp_path: object) -> None:
    import pathlib

    f = pathlib.Path(str(tmp_path)) / "sys.md"
    f.write_text("SYSTEM CONTEXT", encoding="utf-8")
    composed = cp._compose_prompt("user ask", [str(f)])
    assert composed == "SYSTEM CONTEXT\n\nuser ask"


def test_build_copilot_mcp_writes_file_and_flag() -> None:
    mcp = MCPServerConfig(backend_url="http://x", mcp_token="tok", tool_names=["code_query"])
    inv = build_copilot_mcp(mcp)
    try:
        assert inv.args[0] == "--additional-mcp-config"
        assert inv.args[1].startswith("@")
        path = inv.args[1][1:]
        with open(path) as fh:
            data = json.load(fh)
        server = data["mcpServers"][SERVER_NAME]
        assert server["type"] == "local"
        assert server["env"]["BODHIORCHARD_MCP_TOKEN"] == "tok"
        assert server["env"]["BODHIORCHARD_MCP_TOOLS"] == "code_query"
    finally:
        for p in inv.cleanup_paths:
            os.unlink(p)


def test_build_codex_mcp_emits_approval_and_command() -> None:
    mcp = MCPServerConfig(backend_url="http://x", mcp_token="tok", tool_names=[])
    inv = build_codex_mcp(mcp)
    joined = " ".join(inv.args)
    assert f"mcp_servers.{SERVER_NAME}.command=" in joined
    assert f'mcp_servers.{SERVER_NAME}.default_tools_approval_mode="approve"' in joined
    assert inv.cleanup_paths == []


def test_registry_dispatches_on_provider() -> None:
    assert isinstance(provider_for(Organization(ai_provider=AIProvider.copilot)), CopilotProvider)
    assert isinstance(provider_for(Organization(ai_provider=AIProvider.claude)), ClaudeProvider)
    assert isinstance(provider_for(None), ClaudeProvider)


async def test_copilot_run_parses_success() -> None:
    config = ClaudeRunnerConfig(timeout_seconds=30)
    with patch.object(cp, "run_cli", new=AsyncMock(return_value=(0, _SAMPLE_JSONL, ""))):
        result = await CopilotProvider().run("hi", NO_REPO_CONTEXT, config)
    assert result.success is True
    assert result.output == "FINAL ANSWER"
    assert result.cost_usd is None


async def test_copilot_run_reports_failure() -> None:
    config = ClaudeRunnerConfig(timeout_seconds=30)
    with patch.object(cp, "run_cli", new=AsyncMock(return_value=(1, "", "boom"))):
        result = await CopilotProvider().run("hi", NO_REPO_CONTEXT, config)
    assert result.success is False
    assert "boom" in (result.error or "")


def test_emit_progress_fires_on_tool_events_only() -> None:
    seen: list[str] = []
    cb = lambda name, _inp: seen.append(name)  # noqa: E731
    # A tool-invocation event fires with its resolved name.
    cp._emit_progress('{"type":"tool.execution","data":{"name":"bodhi-get_features"}}', cb)
    # Result/output events for the same call must not double-tick.
    cp._emit_progress('{"type":"tool.result","data":{"name":"bodhi-get_features"}}', cb)
    # Non-tool events (the assistant answer) are ignored.
    cp._emit_progress('{"type":"assistant.message","data":{"content":"hi"}}', cb)
    # Junk lines are no-ops.
    cp._emit_progress("not json", cb)
    assert seen == ["bodhi-get_features"]


async def test_copilot_run_streams_progress_when_callback_given() -> None:
    lines = [
        '{"type":"tool.execution","data":{"name":"bodhi-code_query"}}',
        '{"type":"assistant.message","data":{"content":"FINAL ANSWER"}}',
    ]
    stdout = "\n".join(lines)
    seen: list[str] = []

    async def _fake_stream(cmd, cwd, env, timeout, on_line):  # type: ignore[no-untyped-def]
        for ln in stdout.splitlines():
            on_line(ln)
        return (0, stdout, "")

    with patch.object(cp, "run_cli_streaming", new=_fake_stream):
        result = await CopilotProvider().run(
            "hi",
            NO_REPO_CONTEXT,
            ClaudeRunnerConfig(timeout_seconds=30),
            progress_callback=lambda name, _inp: seen.append(name),
        )

    assert result.success is True
    assert result.output == "FINAL ANSWER"
    assert seen == ["bodhi-code_query"]
