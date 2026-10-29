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

"""Merging the Glideship server into a tracked repo's ``.codex/config.toml``.

The file belongs to the repo, so the merge keeps the team's own settings and
servers, replaces a pre-rename server table, writes nothing when the server
is already there, and leaves a file it can't safely edit untouched.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from app.services.repo_codex_toml import codex_server_block, merge_codex_server
from app.services.repo_mcp_json import McpJsonMerge

URL = "http://backend"

# What the setup wrote before the rename, plus a team's own settings around it.
LEGACY_REPO_CONFIG = """model = "o4-mini"
approval_policy = "on-request"

# Added by Bodhiorchard — MCP server for BUD tooling + code intelligence.
[mcp_servers.bodhiorchard]
command = "python3"
args = [".bodhiorchard/mcp_bridge.py"]
default_tools_approval_mode = "approve"

[mcp_servers.bodhiorchard.env]
BODHIORCHARD_BACKEND_URL = "http://old"

[mcp_servers.docs]
command = "npx"
args = ["docs-mcp"]

[mcp_servers.docs.env]
DOCS_TOKEN = "x"
"""


def _config(tmp_path: Path, text: str | None) -> Path:
    path = tmp_path / ".codex" / "config.toml"
    if text is not None:
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
    return path


def test_writes_the_block_when_there_is_no_file(tmp_path: Path) -> None:
    path = _config(tmp_path, None)
    assert merge_codex_server(path, URL) is McpJsonMerge.WRITTEN
    assert path.read_text() == codex_server_block(URL)
    assert merge_codex_server(path, URL) is McpJsonMerge.UNCHANGED


def test_replaces_the_old_server_and_keeps_the_team_settings(tmp_path: Path) -> None:
    path = _config(tmp_path, LEGACY_REPO_CONFIG)

    assert merge_codex_server(path, URL) is McpJsonMerge.WRITTEN

    text = path.read_text()
    config = tomllib.loads(text)
    assert config["model"] == "o4-mini"
    assert config["approval_policy"] == "on-request"
    assert set(config["mcp_servers"]) == {"docs", "glideship"}
    assert config["mcp_servers"]["docs"]["env"] == {"DOCS_TOKEN": "x"}
    assert config["mcp_servers"]["glideship"]["env"] == {"GLIDESHIP_BACKEND_URL": URL}
    assert "Bodhiorchard" not in text
    assert text.count("# Added by Glideship") == 1
    assert merge_codex_server(path, URL) is McpJsonMerge.UNCHANGED


def test_updates_the_backend_url_in_place(tmp_path: Path) -> None:
    path = _config(tmp_path, LEGACY_REPO_CONFIG)
    merge_codex_server(path, URL)

    assert merge_codex_server(path, "http://moved") is McpJsonMerge.WRITTEN

    config = tomllib.loads(path.read_text())
    assert config["mcp_servers"]["glideship"]["env"] == {"GLIDESHIP_BACKEND_URL": "http://moved"}
    assert set(config["mcp_servers"]) == {"docs", "glideship"}


def test_leaves_invalid_toml_alone(tmp_path: Path) -> None:
    broken = "model = \n[mcp_servers.docs\n"
    path = _config(tmp_path, broken)
    assert merge_codex_server(path, URL) is McpJsonMerge.UNUSABLE
    assert path.read_text() == broken


def test_leaves_a_server_defined_inline_alone(tmp_path: Path) -> None:
    # An inline table can't be lifted out line by line, so the file is kept as is.
    inline = '[mcp_servers]\nbodhiorchard = { command = "python3" }\n'
    path = _config(tmp_path, inline)
    assert merge_codex_server(path, URL) is McpJsonMerge.UNUSABLE
    assert path.read_text() == inline
