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

"""Provider-aware first-scan repo config (Codex / Copilot).

Pins the contract that a Codex/Copilot org gets its NATIVE hook config +
AGENTS.md + provider MCP — reusing the shared scripts — and never the
Claude-only ``.claude/`` set. The shared scripts must serve every provider
(``_common.sh`` reads both ``session_id`` and ``sessionId``).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.models.organization import AIProvider
from app.services.scan.agent_repo_config import (
    append_agent_instructions,
    install_agent_hooks,
    write_agent_mcp_config,
)


def test_codex_writes_native_hooks_not_claude(tmp_path: Path) -> None:
    changed = install_agent_hooks(str(tmp_path), "http://backend", AIProvider.codex)
    assert changed is True

    cfg = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    # PascalCase events, wired to the shared scripts.
    assert "SessionStart" in cfg["hooks"]
    assert "PostToolUse" in cfg["hooks"]
    cmd = cfg["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert ".bodhiorchard/hooks/session-start.sh" in cmd

    # Shared scripts live under .bodhiorchard/hooks, NOT .claude.
    assert (tmp_path / ".bodhiorchard" / "hooks" / "_common.sh").exists()
    assert (tmp_path / ".bodhiorchard" / "hooks" / "session-start.sh").exists()
    assert not (tmp_path / ".claude").exists()

    # Idempotent second run.
    assert install_agent_hooks(str(tmp_path), "http://backend", AIProvider.codex) is False


def test_copilot_writes_camelcase_policy(tmp_path: Path) -> None:
    changed = install_agent_hooks(str(tmp_path), "http://backend", AIProvider.copilot)
    assert changed is True

    cfg = json.loads((tmp_path / ".github" / "hooks" / "copilot-cli-policy.json").read_text())
    assert cfg["version"] == 1
    assert "sessionStart" in cfg["hooks"]  # camelCase
    assert "postToolUseFailure" in cfg["hooks"]  # copilot-only event
    entry = cfg["hooks"]["sessionStart"][0]
    assert entry["bash"].endswith(".bodhiorchard/hooks/session-start.sh")
    # No codex config for a copilot org.
    assert not (tmp_path / ".codex").exists()


def test_shared_common_sh_reads_both_session_id_casings(tmp_path: Path) -> None:
    install_agent_hooks(str(tmp_path), "http://backend", AIProvider.codex)
    common = (tmp_path / ".bodhiorchard" / "hooks" / "_common.sh").read_text()
    # One script set serves every provider — Claude/Codex ``session_id`` and
    # Copilot ``sessionId`` both parse.
    assert "session_id" in common
    assert "sessionId" in common


def test_codex_mcp_config_points_at_bridge(tmp_path: Path) -> None:
    changed = write_agent_mcp_config(str(tmp_path), "http://backend", AIProvider.codex)
    assert changed is True

    toml = (tmp_path / ".codex" / "config.toml").read_text()
    assert "[mcp_servers.bodhiorchard]" in toml
    assert ".bodhiorchard/mcp_bridge.py" in toml
    assert "http://backend" in toml
    assert 'default_tools_approval_mode = "approve"' in toml
    # The stdio bridge is copied in for the developer's CLI to spawn.
    assert (tmp_path / ".bodhiorchard" / "mcp_bridge.py").exists()

    assert write_agent_mcp_config(str(tmp_path), "http://backend", AIProvider.codex) is False


def test_agents_md_is_provider_neutral_and_idempotent(tmp_path: Path) -> None:
    changed = append_agent_instructions(str(tmp_path), AIProvider.codex)
    assert changed is True

    md = (tmp_path / "AGENTS.md").read_text()
    assert "Bodhiorchard" in md
    assert ".bodhiorchard/hooks/" in md  # rewritten from .claude/hooks/
    assert "<!-- bodhiorchard:start -->" in md
    assert "<!-- bodhiorchard:end -->" in md

    # Marker-bounded replace → no duplicate section, returns False.
    assert append_agent_instructions(str(tmp_path), AIProvider.codex) is False
    assert (tmp_path / "AGENTS.md").read_text().count("<!-- bodhiorchard:start -->") == 1
