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

"""Repo setup writes Glideship names and migrates pre-rename installs.

A fresh repo gets a ``glideship`` MCP server and ``.glideship/mcp_bridge.py``.
A repo set up before the rename has its ``bodhiorchard`` server entry
replaced (not duplicated), keeps its other MCP servers, and keeps the old
``.bodhiorchard/`` bridge on disk so an unmerged checkout still works.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from app.services.repo_setup import (
    _stage_file_args,
    commit_and_push_setup_worktree,
    init_bodhiorchard_mcp_in_repo,
)

_URL = "http://backend"


def _read_json(path: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads(path.read_text())
    return data


async def test_fresh_repo_gets_glideship_server(tmp_path: Path) -> None:
    assert await init_bodhiorchard_mcp_in_repo(str(tmp_path), _URL) is True

    expected = {
        "command": "python3",
        "args": [".glideship/mcp_bridge.py"],
        "env": {"GLIDESHIP_BACKEND_URL": _URL},
    }
    assert _read_json(tmp_path / ".mcp.json") == {"mcpServers": {"glideship": expected}}
    settings = _read_json(tmp_path / ".claude" / "settings.json")
    assert settings["mcpServers"] == {"glideship": expected}
    assert (tmp_path / ".glideship" / "mcp_bridge.py").is_file()
    assert not (tmp_path / ".bodhiorchard").exists()

    # Idempotent.
    assert await init_bodhiorchard_mcp_in_repo(str(tmp_path), _URL) is False


async def test_legacy_install_is_migrated_in_place(tmp_path: Path) -> None:
    legacy_entry = {
        "command": "python3",
        "args": [".bodhiorchard/mcp_bridge.py"],
        "env": {"BODHIORCHARD_BACKEND_URL": _URL},
    }
    other_server = {"command": "npx", "args": ["some-other-mcp"]}
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"bodhiorchard": legacy_entry}}))
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "mcpServers": {"bodhiorchard": legacy_entry, "other": other_server},
                "hooks": {"Stop": []},
            }
        )
    )
    legacy_bridge = tmp_path / ".bodhiorchard" / "mcp_bridge.py"
    legacy_bridge.parent.mkdir()
    legacy_bridge.write_text("# old bridge\n")

    assert await init_bodhiorchard_mcp_in_repo(str(tmp_path), _URL) is True

    mcp_servers = _read_json(tmp_path / ".mcp.json")["mcpServers"]
    assert isinstance(mcp_servers, dict)
    assert list(mcp_servers) == ["glideship"]

    settings = _read_json(tmp_path / ".claude" / "settings.json")
    servers = settings["mcpServers"]
    assert isinstance(servers, dict)
    assert set(servers) == {"glideship", "other"}
    assert servers["other"] == other_server
    assert settings["hooks"] == {"Stop": []}

    # The old bridge stays until the team merges the setup PR.
    assert legacy_bridge.read_text() == "# old bridge\n"


async def test_claude_setup_keeps_the_repos_own_servers(tmp_path: Path) -> None:
    other_server = {"command": "npx", "args": ["some-other-mcp"]}
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": other_server}}))

    assert await init_bodhiorchard_mcp_in_repo(str(tmp_path), _URL) is True

    mcp_servers = _read_json(tmp_path / ".mcp.json")["mcpServers"]
    assert isinstance(mcp_servers, dict)
    assert set(mcp_servers) == {"other", "glideship"}
    assert mcp_servers["other"] == other_server
    assert await init_bodhiorchard_mcp_in_repo(str(tmp_path), _URL) is False


async def test_missing_bridge_is_restored_when_config_is_current(tmp_path: Path) -> None:
    assert await init_bodhiorchard_mcp_in_repo(str(tmp_path), _URL) is True
    bridge = tmp_path / ".glideship" / "mcp_bridge.py"
    bridge.unlink()

    assert await init_bodhiorchard_mcp_in_repo(str(tmp_path), _URL) is True
    assert bridge.is_file()


async def test_unparseable_mcp_json_is_left_alone(tmp_path: Path) -> None:
    """No bridge or settings entry ships when nothing would point Claude at it."""
    (tmp_path / ".mcp.json").write_text("{ not json")

    assert await init_bodhiorchard_mcp_in_repo(str(tmp_path), _URL) is False
    assert (tmp_path / ".mcp.json").read_text() == "{ not json"
    assert not (tmp_path / ".glideship").exists()
    assert not (tmp_path / ".claude").exists()


def test_glideship_folder_is_force_added() -> None:
    bridge = ".glideship/mcp_bridge.py"
    assert _stage_file_args(bridge) == ["add", "-f", bridge]
    assert _stage_file_args(".mcp.json") == ["add", ".mcp.json"]


async def test_setup_commit_uses_glideship_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Keep the developer's own git config (signing, hooks) out of the commit.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    await init_bodhiorchard_mcp_in_repo(str(tmp_path), _URL)

    assert await commit_and_push_setup_worktree(str(tmp_path)) is not None

    log = subprocess.run(
        ["git", "log", "-1", "--format=%an <%ae>%n%B"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    author, subject = log.splitlines()[:2]
    assert author == "Glideship <glideship@users.noreply.github.com>"
    assert subject == "chore(glideship): add MCP tools, git hooks, and config"
    assert ".glideship/mcp_bridge.py" in log
    committed = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert ".glideship/mcp_bridge.py" in committed
