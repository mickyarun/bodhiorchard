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

"""Merging the Glideship server into a tracked repo's ``.mcp.json``.

The file belongs to the repo, so the merge keeps the repo's own servers and
top-level keys, replaces a pre-rename entry, writes nothing when the server is
already there, and leaves a file it can't parse untouched. Copilot reads
only one MCP file per directory, so its file is whichever one already exists.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.repo_mcp_json import (
    GITHUB_MCP_JSON,
    MCP_JSON,
    McpJsonMerge,
    copilot_mcp_json,
    merge_glideship_server,
)
from app.services.repo_setup_names import (
    LEGACY_MCP_SERVER_KEY,
    MCP_SERVER_KEY,
    mcp_server_entry,
)

_URL = "http://backend"
_OTHER = {"command": "npx", "args": ["some-other-mcp"]}


def _servers(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text())
    servers: dict[str, object] = data["mcpServers"]
    return servers


def test_fresh_repo_gets_only_glideship(tmp_path: Path) -> None:
    path = tmp_path / MCP_JSON
    assert merge_glideship_server(path, _URL) is McpJsonMerge.WRITTEN
    assert _servers(path) == {MCP_SERVER_KEY: mcp_server_entry(_URL)}
    assert merge_glideship_server(path, _URL) is McpJsonMerge.UNCHANGED


def test_repo_servers_and_keys_are_kept(tmp_path: Path) -> None:
    path = tmp_path / MCP_JSON
    path.write_text(json.dumps({"mcpServers": {"other": _OTHER}, "inputs": [{"id": "x"}]}))

    assert merge_glideship_server(path, _URL) is McpJsonMerge.WRITTEN

    data = json.loads(path.read_text())
    assert data["inputs"] == [{"id": "x"}]
    assert data["mcpServers"] == {"other": _OTHER, MCP_SERVER_KEY: mcp_server_entry(_URL)}


@pytest.mark.parametrize("has_current_entry", [False, True])
def test_pre_rename_entry_is_replaced(tmp_path: Path, has_current_entry: bool) -> None:
    """A leftover legacy entry is dropped even next to an up-to-date one."""
    servers: dict[str, object] = {LEGACY_MCP_SERVER_KEY: {"command": "python3"}, "other": _OTHER}
    if has_current_entry:
        servers[MCP_SERVER_KEY] = mcp_server_entry(_URL)
    path = tmp_path / MCP_JSON
    path.write_text(json.dumps({"mcpServers": servers}))

    assert merge_glideship_server(path, _URL) is McpJsonMerge.WRITTEN
    assert set(_servers(path)) == {"other", MCP_SERVER_KEY}


def test_up_to_date_file_is_not_rewritten(tmp_path: Path) -> None:
    """The team's own formatting survives a re-run that has nothing to add."""
    servers = {"other": _OTHER, MCP_SERVER_KEY: mcp_server_entry(_URL)}
    original = json.dumps({"mcpServers": servers}, separators=(",", ":"))
    path = tmp_path / MCP_JSON
    path.write_text(original)

    assert merge_glideship_server(path, _URL) is McpJsonMerge.UNCHANGED
    assert path.read_text() == original


@pytest.mark.parametrize(
    "content",
    ["{ not json", "[]", '{"mcpServers": ["glideship"]}'],
    ids=["invalid-json", "not-an-object", "servers-not-an-object"],
)
def test_unusable_file_is_left_alone(tmp_path: Path, content: str) -> None:
    path = tmp_path / MCP_JSON
    path.write_text(content)

    assert merge_glideship_server(path, _URL) is McpJsonMerge.UNUSABLE
    assert path.read_text() == content


@pytest.mark.parametrize(
    ("existing", "expected"),
    [
        ([], MCP_JSON),
        ([GITHUB_MCP_JSON], GITHUB_MCP_JSON),
        ([MCP_JSON, GITHUB_MCP_JSON], MCP_JSON),
    ],
    ids=["neither", "github-only", "both"],
)
def test_copilot_file_is_the_one_copilot_reads(
    tmp_path: Path, existing: list[str], expected: str
) -> None:
    """Creating ``.mcp.json`` would hide a repo's ``.github/mcp.json`` from Copilot."""
    for name in existing:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("{}")
    assert copilot_mcp_json(tmp_path) == tmp_path / expected
