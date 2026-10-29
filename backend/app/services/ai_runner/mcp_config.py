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

"""Per-provider MCP wiring for the Glideship stdio bridge.

Claude handles its own ``--mcp-config`` inside ``claude_runner``; this module
serves Copilot and Codex, which take the bridge via a per-invocation flag
(no global config-dir relocation needed):

- Copilot: a temp JSON file passed as ``--additional-mcp-config @<file>``.
- Codex: ``-c mcp_servers.<name>.*`` overrides, incl. the approval mode that
  stops non-interactive MCP calls from auto-cancelling.

Both spawn the same ``stdio_bridge.py`` with the same org-scoped token, so the
bridge code is shared and untouched.

Every run also switches off, by name, the servers repo setup writes into a
tracked repo. Both CLIs load a repo's own MCP config once the folder is
trusted (Codex: ``.codex/config.toml``; Copilot: ``.mcp.json`` or
``.github/mcp.json``), and those entries carry no token, so a run would
otherwise start a second, unauthenticated bridge. Other servers in the repo
or user config still load; neither CLI has a flag to skip workspace config.
"""

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.mcp.bridge_env import BACKEND_URL_ENV, MCP_TOKEN_ENV, MCP_TOKEN_FILE_ENV, MCP_TOOLS_ENV
from app.services.claude_runner import MCPServerConfig
from app.services.repo_setup_names import LEGACY_MCP_SERVER_KEY, MCP_SERVER_KEY

# The MCP server label the CLIs use. Copilot namespaces tools as
# ``<server>-<tool>`` (e.g. ``bodhiorchard-code_query``); Codex keeps the bare
# tool name. Adapters that allow-list tools must account for this.
SERVER_NAME = "bodhiorchard"

_BRIDGE_PATH = str(Path(__file__).resolve().parents[2] / "mcp" / "stdio_bridge.py")

# Every key repo setup has written for its server, current and pre-rename.
_REPO_SERVER_KEYS = (MCP_SERVER_KEY, LEGACY_MCP_SERVER_KEY)


@dataclass
class McpInvocation:
    """CLI args to wire the bridge, plus any temp files to clean up after."""

    args: list[str] = field(default_factory=list)
    cleanup_paths: list[str] = field(default_factory=list)


def _bridge_env(mcp: MCPServerConfig) -> dict[str, str]:
    """Env the bridge subprocess needs to reach the backend (see stdio_bridge)."""
    return {
        BACKEND_URL_ENV: mcp.backend_url,
        MCP_TOKEN_ENV: mcp.mcp_token,
        MCP_TOKEN_FILE_ENV: "",
        MCP_TOOLS_ENV: ",".join(mcp.tool_names),
    }


def _repo_server_keys_off(mcp: MCPServerConfig | None) -> list[str]:
    """Repo-setup server keys to switch off for this run.

    The legacy key is the bridge's own name, so when the bridge runs its
    per-run entry takes that name over and must stay on.
    """
    bridge_key = SERVER_NAME if mcp is not None else None
    return [key for key in _REPO_SERVER_KEYS if key != bridge_key]


def build_copilot_mcp(mcp: MCPServerConfig | None) -> McpInvocation:
    """Write a Copilot ``--additional-mcp-config`` file for the bridge.

    ``--disable-mcp-server`` is passed on every run, with or without the
    bridge. Copilot accepts a name that no config defines, so the flag is
    safe in repos that were never set up.
    """
    repo_server_off: list[str] = []
    for key in _repo_server_keys_off(mcp):
        repo_server_off += ["--disable-mcp-server", key]
    if mcp is None:
        return McpInvocation(args=repo_server_off)
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
    return McpInvocation(
        args=[*repo_server_off, "--additional-mcp-config", f"@{path}"], cleanup_paths=[path]
    )


def _codex_config_args(overrides: dict[str, object]) -> list[str]:
    """Encode ``overrides`` as Codex ``-c key=value`` pairs.

    Values are TOML-encoded via ``json.dumps`` (JSON scalars/arrays are valid
    TOML).
    """
    args: list[str] = []
    for key, value in overrides.items():
        args += ["-c", f"{key}={json.dumps(value)}"]
    return args


def _codex_repo_servers_off(mcp: MCPServerConfig | None) -> dict[str, object]:
    """Overrides that keep the repo's own servers from starting.

    ``-c`` values merge into a trusted project's table rather than replace it.
    Where no such server exists, a bare ``enabled=false`` is an entry with no
    transport and Codex refuses to load its config, so a ``command`` is set as
    well. A disabled server is never spawned, so that command never runs.
    """
    overrides: dict[str, object] = {}
    for key in _repo_server_keys_off(mcp):
        overrides[f"mcp_servers.{key}.command"] = sys.executable
        overrides[f"mcp_servers.{key}.enabled"] = False
    return overrides


def build_codex_mcp(mcp: MCPServerConfig | None) -> McpInvocation:
    """Build Codex ``-c mcp_servers.*`` overrides for the bridge.

    ``default_tools_approval_mode=approve`` is required, else Codex
    auto-cancels MCP calls in non-interactive ``exec`` mode. The repo's own
    servers are switched off on every run, with or without the bridge.
    """
    overrides = _codex_repo_servers_off(mcp)
    if mcp is None:
        return McpInvocation(args=_codex_config_args(overrides))
    base = f"mcp_servers.{SERVER_NAME}"
    overrides |= {
        f"{base}.command": sys.executable,
        f"{base}.args": [_BRIDGE_PATH],
        f"{base}.default_tools_approval_mode": "approve",
    }
    for key, value in _bridge_env(mcp).items():
        overrides[f"{base}.env.{key}"] = value
    return McpInvocation(args=_codex_config_args(overrides))
