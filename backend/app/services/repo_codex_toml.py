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

"""The Glideship server in a tracked repo's ``.codex/config.toml``.

The file belongs to the repo: teams keep their own model, sandbox and MCP
settings in it. Repo setup replaces only the ``mcp_servers.glideship`` table
(and a pre-rename ``mcp_servers.bodhiorchard`` one, with their sub-tables)
and keeps every other line. A file that isn't valid TOML, or that defines
the server in a form the line splice can't take out cleanly, is left alone.
"""

import re
import tomllib
from pathlib import Path

import structlog

from app.mcp.bridge_env import BACKEND_URL_ENV
from app.services.repo_mcp_json import McpJsonMerge
from app.services.repo_setup_names import BRIDGE_PATH, LEGACY_MCP_SERVER_KEY, MCP_SERVER_KEY

logger = structlog.get_logger(__name__)

CODEX_CONFIG = ".codex/config.toml"

_BLOCK_COMMENT = "# Added by Glideship — MCP server for BUD tooling + code intelligence."
# The same line as written before the rename; dropped along with the old table.
_BLOCK_COMMENTS = (_BLOCK_COMMENT, _BLOCK_COMMENT.replace("Glideship", "Bodhiorchard"))
_OUR_KEYS = (MCP_SERVER_KEY, LEGACY_MCP_SERVER_KEY)
_HEADER = re.compile(r"^\s*\[\[?\s*([^\[\]]+?)\s*\]\]?\s*(#.*)?$")


def codex_server_block(backend_url: str) -> str:
    """The ``[mcp_servers.glideship]`` tables pointing at the shared stdio bridge.

    ``default_tools_approval_mode = "approve"`` lets the Glideship tools run
    without a per-call approval prompt (mirrors the per-invocation flag the
    backend adapter passes), so BUD-todo claims don't stall.
    """
    return (
        f"{_BLOCK_COMMENT}\n"
        f"[mcp_servers.{MCP_SERVER_KEY}]\n"
        'command = "python3"\n'
        f'args = ["{BRIDGE_PATH}"]\n'
        'default_tools_approval_mode = "approve"\n\n'
        f"[mcp_servers.{MCP_SERVER_KEY}.env]\n"
        f'{BACKEND_URL_ENV} = "{backend_url}"\n'
    )


def _is_ours(header: str) -> bool:
    """True for ``mcp_servers.<our key>`` and any of its sub-tables."""
    parts = [part.strip().strip("\"'") for part in header.split(".")]
    return len(parts) >= 2 and parts[0] == "mcp_servers" and parts[1] in _OUR_KEYS


def _without_our_tables(text: str) -> str:
    """``text`` minus our server tables and the comment line written above them."""
    kept: list[str] = []
    skipping = False
    for line in text.splitlines():
        header = _HEADER.match(line)
        if header:
            skipping = _is_ours(header.group(1))
            if skipping and kept and kept[-1].strip() in _BLOCK_COMMENTS:
                kept.pop()
        if not skipping:
            kept.append(line)
    return "\n".join(kept).strip()


def _has_our_server(text: str) -> bool:
    servers = tomllib.loads(text).get("mcp_servers", {})
    return isinstance(servers, dict) and any(key in servers for key in _OUR_KEYS)


def merge_codex_server(path: Path, backend_url: str) -> McpJsonMerge:
    """Put the Glideship server into the Codex config at ``path``, keeping the rest."""
    block = codex_server_block(backend_url)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        tomllib.loads(existing)
        rest = _without_our_tables(existing)
        if _has_our_server(rest):
            raise ValueError("server defined outside its own table")
        updated = f"{rest}\n\n{block}" if rest else block
        tomllib.loads(updated)
    except (tomllib.TOMLDecodeError, ValueError):
        logger.warning("codex_config_unreadable_left_alone", path=str(path))
        return McpJsonMerge.UNUSABLE

    if updated == existing:
        return McpJsonMerge.UNCHANGED
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")
    return McpJsonMerge.WRITTEN
