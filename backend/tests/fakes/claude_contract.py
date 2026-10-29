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

"""Read a ``claude`` command line the way the CLI would, and flag what it rejects.

:func:`parse_argv` turns argv plus the ``--mcp-config`` file into an
:class:`AgentRun`. :func:`contract_problems` lists the things the real CLI
or the MCP bridge would refuse (``stream-json`` without ``--verbose``, an
MCP server that does not point at an existing bridge script, an empty
backend URL or token), so a regression in how the app builds the command
fails the test instead of passing against a lenient fake.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.mcp.bridge_env import BACKEND_URL_ENV, MCP_TOKEN_ENV, MCP_TOOLS_ENV
from tests.fakes.claude_script import AgentRun

MCP_SERVER = "bodhiorchard"
MCP_PREFIX = f"mcp__{MCP_SERVER}__"


def parse_argv(argv: list[str], cwd: str | None, env: dict[str, str]) -> AgentRun:
    """The run described by one ``claude`` command line."""
    run = AgentRun(argv=argv, prompt="", cwd=cwd, env=env, output_format="json")
    run.prompt = run.flag("-p") or ""
    run.output_format = run.flag("--output-format") or "json"
    allowed = run.flag("--allowedTools")
    run.allowed_tools = allowed.split(",") if allowed else []
    config_path = run.flag("--mcp-config")
    if config_path:
        run.mcp_config = json.loads(Path(config_path).read_text())
        server_env = run.mcp_config["mcpServers"][MCP_SERVER]["env"]
        run.mcp_backend_url = server_env.get(BACKEND_URL_ENV)
        run.mcp_token = server_env.get(MCP_TOKEN_ENV)
        tools = server_env.get(MCP_TOOLS_ENV, "")
        run.mcp_tools = [t for t in tools.split(",") if t]
    return run


def contract_problems(run: AgentRun) -> list[str]:
    """What the real CLI or bridge would reject about this command line."""
    problems: list[str] = []
    if run.output_format == "stream-json" and "--verbose" not in run.argv:
        problems.append("--output-format stream-json requires --verbose")
    if not run.prompt:
        problems.append("empty -p prompt")
    if run.mcp_config is not None:
        server = run.mcp_config["mcpServers"][MCP_SERVER]
        bridge = (server.get("args") or [""])[0]
        if not Path(server.get("command", "")).exists() or not Path(bridge).is_file():
            problems.append(f"MCP server does not launch the bridge script: {server}")
        if not run.mcp_backend_url or not run.mcp_token:
            problems.append("MCP config without a backend URL or token")
    return problems


def tool_allowed(run: AgentRun, tool: str) -> bool:
    """Whether the CLI would let the model call ``tool`` in this run."""
    if run.mcp_tools and tool not in run.mcp_tools:
        return False
    if not run.allowed_tools:
        return True
    rules = {rule.strip() for rule in run.allowed_tools}
    return bool(rules & {f"mcp__{MCP_SERVER}", MCP_PREFIX + tool})
