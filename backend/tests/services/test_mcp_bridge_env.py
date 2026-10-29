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

"""The bridge and the hook scripts read the token under both names.

``GLIDESHIP_MCP_TOKEN`` is the name the UI now tells developers to export;
``BODHIORCHARD_MCP_TOKEN`` is what every shell profile and committed hook set
up before the rename uses. Both must work, and the new name must win so a
stale legacy export can't shadow a freshly generated token. A new name that is
set but blank still wins, so an explicit per-run value is authoritative.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from app.mcp import stdio_bridge
from app.mcp.bridge_env import (
    BACKEND_URL_ENV,
    LEGACY_MCP_TOKEN_ENV,
    MCP_TOKEN_ENV,
    MCP_TOKEN_FILE_ENV,
    MCP_TOOLS_ENV,
)
from app.services.repo_setup import _build_common_sh

_NEW = MCP_TOKEN_ENV
_OLD = LEGACY_MCP_TOKEN_ENV

# (env set, token the bridge and hooks should use)
_CASES = [
    ({_NEW: "new-tok"}, "new-tok"),
    ({_OLD: "old-tok"}, "old-tok"),
    ({_NEW: "new-tok", _OLD: "old-tok"}, "new-tok"),
    ({_NEW: "", _OLD: "old-tok"}, ""),
    ({}, ""),
]


def test_bridge_prefixes_match_the_names_writers_use() -> None:
    # The bridge is copied into repos and can't import ``bridge_env``; this
    # keeps its own prefixes in step with the constants everything writes.
    new_prefix, legacy_prefix = stdio_bridge._ENV_PREFIXES
    for name in (BACKEND_URL_ENV, MCP_TOKEN_ENV, MCP_TOKEN_FILE_ENV, MCP_TOOLS_ENV):
        assert name.startswith(new_prefix)
    assert MCP_TOKEN_ENV.replace(new_prefix, legacy_prefix) == LEGACY_MCP_TOKEN_ENV


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for prefix in ("GLIDESHIP_", "BODHIORCHARD_"):
        for suffix in ("MCP_TOKEN", "MCP_TOKEN_FILE", "MCP_TOOLS", "BACKEND_URL"):
            monkeypatch.delenv(f"{prefix}{suffix}", raising=False)
    return monkeypatch


@pytest.mark.parametrize(("env", "expected"), _CASES)
def test_bridge_token_prefers_new_name(
    clean_env: pytest.MonkeyPatch, env: dict[str, str], expected: str
) -> None:
    for key, value in env.items():
        clean_env.setenv(key, value)
    assert stdio_bridge._get_token() == expected


def test_bridge_reads_token_file_under_either_name(
    clean_env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    token_file = tmp_path / "mcp_token"
    token_file.write_text("file-tok\n")
    clean_env.setenv("BODHIORCHARD_MCP_TOKEN_FILE", str(token_file))
    assert stdio_bridge._get_token() == "file-tok"

    clean_env.delenv("BODHIORCHARD_MCP_TOKEN_FILE")
    clean_env.setenv("GLIDESHIP_MCP_TOKEN_FILE", str(token_file))
    assert stdio_bridge._get_token() == "file-tok"


def test_bridge_backend_url_falls_back_to_legacy(clean_env: pytest.MonkeyPatch) -> None:
    assert stdio_bridge._env("BACKEND_URL", "http://default") == "http://default"
    clean_env.setenv("BODHIORCHARD_BACKEND_URL", "http://old")
    assert stdio_bridge._env("BACKEND_URL", "http://default") == "http://old"
    clean_env.setenv("GLIDESHIP_BACKEND_URL", "http://new")
    assert stdio_bridge._env("BACKEND_URL", "http://default") == "http://new"


@pytest.mark.parametrize(("env", "expected"), _CASES)
def test_hook_common_sh_prefers_new_name(
    tmp_path: Path, env: dict[str, str], expected: str
) -> None:
    common = tmp_path / "_common.sh"
    common.write_text(_build_common_sh("http://backend"))
    # Run the real script under POSIX sh with only the vars under test set.
    result = subprocess.run(
        ["sh", "-c", f'. "{common}"; printf "%s" "$TOKEN"'],
        env={"PATH": os.environ["PATH"], **env},
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == expected
