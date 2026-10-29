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

"""The Glideship server in a tracked repo's ``.mcp.json``.

Claude Code and the Copilot CLI both read the repo-root ``.mcp.json`` in the
``mcpServers`` shape, so repo setup writes one entry there for either
provider. The entry has no ``type``: Claude reads that as ``stdio`` and
Copilot as ``local``, and Copilot exposes all of a server's tools when
``tools`` is left out.

The file belongs to the repo. Every other server in it is kept, and a file
that can't be parsed is left alone rather than replaced.

Copilot reads only one MCP file per directory: ``.mcp.json`` if it exists,
else ``.github/mcp.json``. Creating ``.mcp.json`` in a repo that keeps its
servers in ``.github/mcp.json`` would hide them, so the Copilot path merges
into whichever of the two Copilot already reads.
"""

import json
import shutil
from enum import Enum
from pathlib import Path

import structlog

from app.services.repo_setup_names import (
    BRIDGE_PATH,
    LEGACY_MCP_SERVER_KEY,
    MCP_SERVER_KEY,
    mcp_server_entry,
)

logger = structlog.get_logger(__name__)

MCP_JSON = ".mcp.json"
GITHUB_MCP_JSON = ".github/mcp.json"

_SOURCE_BRIDGE = Path(__file__).resolve().parents[1] / "mcp" / "stdio_bridge.py"


def copy_mcp_bridge(repo: Path) -> None:
    """Copy the stdio bridge into the repo at ``BRIDGE_PATH``."""
    dest = repo / BRIDGE_PATH
    dest.parent.mkdir(exist_ok=True)
    shutil.copy2(_SOURCE_BRIDGE, dest)


class McpJsonMerge(Enum):
    """What ``merge_glideship_server`` did to the file."""

    WRITTEN = "written"
    UNCHANGED = "unchanged"
    UNUSABLE = "unusable"  # couldn't be parsed; left as it was


def copilot_mcp_json(repo: Path) -> Path:
    """The MCP file Copilot reads in ``repo``: the first that exists, else ``.mcp.json``."""
    for name in (MCP_JSON, GITHUB_MCP_JSON):
        if (repo / name).exists():
            return repo / name
    return repo / MCP_JSON


def _read_config(path: Path) -> tuple[dict[str, object], dict[str, object]] | None:
    """The parsed ``.mcp.json`` and its servers; None if the file can't be used.

    A missing file reads as empty.
    """
    if not path.exists():
        return {}, {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    servers = data.get("mcpServers", {})
    if not isinstance(servers, dict):
        return None
    return data, servers


def merge_glideship_server(path: Path, backend_url: str) -> McpJsonMerge:
    """Put the Glideship server into the MCP file at ``path``, keeping the rest.

    A pre-rename ``bodhiorchard`` entry is replaced so the tools aren't
    registered twice.
    """
    parsed = _read_config(path)
    if parsed is None:
        logger.warning("mcp_json_unreadable_left_alone", path=str(path))
        return McpJsonMerge.UNUSABLE

    config, servers = parsed
    merged = {key: value for key, value in servers.items() if key != LEGACY_MCP_SERVER_KEY}
    merged[MCP_SERVER_KEY] = mcp_server_entry(backend_url)
    if path.exists() and merged == servers:
        return McpJsonMerge.UNCHANGED

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**config, "mcpServers": merged}, indent=2), encoding="utf-8")
    return McpJsonMerge.WRITTEN
