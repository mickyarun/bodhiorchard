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

"""Per-provider MCP wiring for the bodhiorchard stdio bridge.

Claude handles its own ``--mcp-config`` inside ``claude_runner``; this module
serves Copilot and Codex, which take the bridge via a per-invocation flag
(verified in the Phase-0 spike — no global config-dir relocation needed):

- Copilot: a temp JSON file passed as ``--additional-mcp-config @<file>``.
- Codex: ``-c mcp_servers.<name>.*`` overrides, incl. the approval mode that
  stops non-interactive MCP calls from auto-cancelling.

Both spawn the same ``stdio_bridge.py`` with the same org-scoped token, so the
bridge code is shared and untouched.
"""

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.services.claude_runner import MCPServerConfig

# The MCP server label the CLIs use. Copilot namespaces tools as
# ``<server>-<tool>`` (e.g. ``bodhiorchard-code_query``); Codex keeps the bare
# tool name. Adapters that allow-list tools must account for this.
SERVER_NAME = "bodhiorchard"

_BRIDGE_PATH = str(Path(__file__).resolve().parents[2] / "mcp" / "stdio_bridge.py")


@dataclass
class McpInvocation:
    """CLI args to wire the bridge, plus any temp files to clean up after."""

    args: list[str] = field(default_factory=list)
    cleanup_paths: list[str] = field(default_factory=list)


def _bridge_env(mcp: MCPServerConfig) -> dict[str, str]:
    """Env the bridge subprocess needs to reach the backend (see stdio_bridge)."""
    return {
        "BODHIORCHARD_BACKEND_URL": mcp.backend_url,
        "BODHIORCHARD_MCP_TOKEN": mcp.mcp_token,
        "BODHIORCHARD_MCP_TOOLS": ",".join(mcp.tool_names),
    }


def build_copilot_mcp(mcp: MCPServerConfig | None) -> McpInvocation:
    """Write a Copilot ``--additional-mcp-config`` file for the bridge."""
    if mcp is None:
        return McpInvocation()
    config = {
        "mcpServers": {
            SERVER_NAME: {
                "type": "local",
                "command": sys.executable,
                "args": [_BRIDGE_PATH],
                "tools": ["*"],
                "env": _bridge_env(mcp),
            }
        }
    }
    fd, path = tempfile.mkstemp(prefix="bodhiorchard_copilot_mcp_", suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(config, fh)
    os.chmod(path, 0o600)
    return McpInvocation(args=["--additional-mcp-config", f"@{path}"], cleanup_paths=[path])


def build_codex_mcp(mcp: MCPServerConfig | None) -> McpInvocation:
    """Build Codex ``-c mcp_servers.*`` overrides for the bridge.

    Values are TOML-encoded via ``json.dumps`` (JSON scalars/arrays are valid
    TOML). ``default_tools_approval_mode=approve`` is required, else Codex
    auto-cancels MCP calls in non-interactive ``exec`` mode.
    """
    if mcp is None:
        return McpInvocation()
    base = f"mcp_servers.{SERVER_NAME}"
    overrides: dict[str, object] = {
        f"{base}.command": sys.executable,
        f"{base}.args": [_BRIDGE_PATH],
        f"{base}.default_tools_approval_mode": "approve",
    }
    for key, value in _bridge_env(mcp).items():
        overrides[f"{base}.env.{key}"] = value

    args: list[str] = []
    for key, override in overrides.items():
        args += ["-c", f"{key}={json.dumps(override)}"]
    return McpInvocation(args=args)
