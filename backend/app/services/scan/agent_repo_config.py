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

"""Provider-aware first-scan repo config for Codex / Copilot.

The Claude path (``repo_setup.install_claude_hooks`` /
``init_bodhiorchard_mcp_in_repo`` / ``append_bodhiorchard_claude_instructions``)
writes ``.claude/`` config that only the Claude CLI reads. Codex and Copilot
have their own — but equivalent — hook systems (command hooks, stdin-JSON
payload, exit 0/2 contract), so the *same* dev-activity + BUD-todo scripts
work for all three; only the config file that wires scripts→events differs.

This module writes, for a Codex/Copilot org:
  * the shared hook scripts under ``.bodhiorchard/hooks/`` (reusing the
    ``repo_setup._build_*_sh`` builders — one source of truth),
  * the provider-native hook config (``.codex/hooks.json`` /
    ``.github/hooks/copilot-cli-policy.json``),
  * the provider MCP config (``.codex/config.toml`` /
    ``.github/copilot/mcp-config.json``), pointing at the shared
    ``.bodhiorchard/mcp_bridge.py``,
  * ``AGENTS.md`` (the provider-neutral form of the CLAUDE.md section).

The generic files (``.githooks/``, ``.gitignore``, ``package.json`` prepare,
the MCP bridge) are written for every provider by the existing helpers.
"""

from __future__ import annotations

import contextlib
import json
import shutil
from pathlib import Path

import structlog

from app.models.organization import AIProvider
from app.services.repo_setup import (
    _BG_END,
    _BG_START,
    _BODHIORCHARD_CLAUDE_SECTION,
    _build_activity_report_sh,
    _build_api_error_track_sh,
    _build_common_sh,
    _build_detect_bud_prompt_sh,
    _build_file_change_track_sh,
    _build_post_commit_track_sh,
    _build_session_end_sh,
    _build_session_start_sh,
    _build_subagent_start_sh,
    _build_subagent_stop_sh,
    _build_tool_error_track_sh,
)

logger = structlog.get_logger(__name__)

# Where the shared scripts live for non-Claude providers. Under
# ``.bodhiorchard/`` (gitignored → force-added by ``_stage_file_args``) so
# the repo root stays uncluttered and the dir name signals ownership.
_HOOKS_SUBDIR = ".bodhiorchard/hooks"


def _shared_scripts(backend_url: str) -> list[tuple[str, str]]:
    """The (filename, contents) hook scripts, reused across providers."""
    return [
        ("_common.sh", _build_common_sh(backend_url)),
        ("session-start.sh", _build_session_start_sh()),
        ("session-end.sh", _build_session_end_sh()),
        ("post-commit-track.sh", _build_post_commit_track_sh()),
        ("file-change-track.sh", _build_file_change_track_sh()),
        ("tool-error-track.sh", _build_tool_error_track_sh()),
        ("api-error-track.sh", _build_api_error_track_sh()),
        ("activity-report.sh", _build_activity_report_sh()),
        ("detect-bud-prompt.sh", _build_detect_bud_prompt_sh()),
        ("subagent-start.sh", _build_subagent_start_sh()),
        ("subagent-stop.sh", _build_subagent_stop_sh()),
    ]


def _write_shared_scripts(repo: Path, backend_url: str) -> bool:
    """Write the shared hook scripts under ``.bodhiorchard/hooks/``. Idempotent."""
    hooks_dir = repo / _HOOKS_SUBDIR
    hooks_dir.mkdir(parents=True, exist_ok=True)
    changed = False
    for filename, content in _shared_scripts(backend_url):
        path = hooks_dir / filename
        existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else None
        if existing is not None and existing.strip() == content.strip():
            continue
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)
        changed = True
    return changed


# Claude event name → shared script. Codex reuses these PascalCase names
# verbatim (minus the events it lacks); Copilot maps them to camelCase below.
# ``None`` matcher = fire on every invocation of that event.
_CODEX_HOOKS: dict[str, list[tuple[str | None, str]]] = {
    "SessionStart": [("startup|resume", "session-start.sh")],
    "PostToolUse": [
        ("Bash|Shell|shell", "post-commit-track.sh"),
        ("Edit|Write|str_replace|apply_patch", "file-change-track.sh"),
    ],
    "Stop": [(None, "activity-report.sh")],
    "UserPromptSubmit": [(None, "detect-bud-prompt.sh")],
    "SubagentStart": [(None, "subagent-start.sh")],
    "SubagentStop": [(None, "subagent-stop.sh")],
}

# Copilot uses camelCase events, a ``bash`` key, and has sessionEnd +
# postToolUseFailure + errorOccurred (which Codex lacks).
_COPILOT_HOOKS: dict[str, list[tuple[str | None, str]]] = {
    "sessionStart": [(None, "session-start.sh")],
    "sessionEnd": [(None, "session-end.sh")],
    "postToolUse": [
        ("bash|shell", "post-commit-track.sh"),
        ("edit|write|str_replace|apply_patch", "file-change-track.sh"),
    ],
    "postToolUseFailure": [(None, "tool-error-track.sh")],
    "agentStop": [(None, "activity-report.sh")],
    "errorOccurred": [(None, "api-error-track.sh")],
    "userPromptSubmitted": [(None, "detect-bud-prompt.sh")],
    "subagentStart": [(None, "subagent-start.sh")],
    "subagentStop": [(None, "subagent-stop.sh")],
}


def _codex_hooks_config() -> dict[str, object]:
    """Build ``.codex/hooks.json`` (Claude-style schema, command hooks)."""
    hooks: dict[str, object] = {}
    for event, entries in _CODEX_HOOKS.items():
        groups = []
        for matcher, script in entries:
            group: dict[str, object] = {
                "hooks": [
                    {"type": "command", "command": f"sh {_HOOKS_SUBDIR}/{script}", "timeout": 15}
                ]
            }
            if matcher is not None:
                group["matcher"] = matcher
            groups.append(group)
        hooks[event] = groups
    return {"hooks": hooks}


def _copilot_hooks_config() -> dict[str, object]:
    """Build ``.github/hooks/copilot-cli-policy.json`` (camelCase, bash key)."""
    hooks: dict[str, object] = {}
    for event, entries in _COPILOT_HOOKS.items():
        items = []
        for matcher, script in entries:
            item: dict[str, object] = {
                "type": "command",
                "bash": f"bash {_HOOKS_SUBDIR}/{script}",
                "timeoutSec": 15,
            }
            if matcher is not None:
                item["matcher"] = matcher
            items.append(item)
        hooks[event] = items
    return {"version": 1, "hooks": hooks}


def _write_json_if_changed(path: Path, data: dict[str, object]) -> bool:
    """Write ``data`` as pretty JSON iff it differs from the current file."""
    expected = json.dumps(data, indent=2)
    if path.exists():
        with contextlib.suppress(OSError):
            if path.read_text(encoding="utf-8", errors="replace").strip() == expected.strip():
                return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(expected, encoding="utf-8")
    return True


def _codex_config_toml(backend_url: str) -> str:
    """``.codex/config.toml`` MCP block pointing at the shared stdio bridge.

    ``default_tools_approval_mode = "approve"`` lets the bodhiorchard tools
    run without a per-call approval prompt (mirrors the per-invocation flag
    the backend adapter passes), so BUD-todo claims don't stall.
    """
    return (
        "# Added by Bodhiorchard — MCP server for BUD tooling + code intelligence.\n"
        "[mcp_servers.bodhiorchard]\n"
        'command = "python3"\n'
        'args = [".bodhiorchard/mcp_bridge.py"]\n'
        'default_tools_approval_mode = "approve"\n\n'
        "[mcp_servers.bodhiorchard.env]\n"
        f'BODHIORCHARD_BACKEND_URL = "{backend_url}"\n'
    )


def _write_codex_config_toml(repo: Path, backend_url: str) -> bool:
    """Write/replace the bodhiorchard block in ``.codex/config.toml``. Idempotent."""
    block = _codex_config_toml(backend_url)
    path = repo / ".codex" / "config.toml"
    existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else None
    if existing is not None and existing.strip() == block.strip():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(block, encoding="utf-8")
    return True


def _mcp_json_config(backend_url: str) -> dict[str, object]:
    """Standard ``mcpServers`` shape shared by the copilot MCP file."""
    return {
        "mcpServers": {
            "bodhiorchard": {
                "command": "python3",
                "args": [".bodhiorchard/mcp_bridge.py"],
                "env": {"BODHIORCHARD_BACKEND_URL": backend_url},
            }
        }
    }


def _copy_mcp_bridge(repo: Path) -> None:
    """Copy the STDIO bridge into the repo (shared by every provider's MCP)."""
    source = Path(__file__).resolve().parents[2] / "mcp" / "stdio_bridge.py"
    dest_dir = repo / ".bodhiorchard"
    dest_dir.mkdir(exist_ok=True)
    shutil.copy2(source, dest_dir / "mcp_bridge.py")


def _agents_md_section() -> str:
    """Provider-neutral form of the CLAUDE.md workflow section for AGENTS.md."""
    return (
        _BODHIORCHARD_CLAUDE_SECTION.replace(".claude/hooks/", f"{_HOOKS_SUBDIR}/")
        .replace("Restart Claude Code", "Restart your agent CLI")
        .replace("Claude Code hooks", "Agent CLI hooks")
        .replace("Claude Code", "your agent CLI")
    )


def install_agent_hooks(repo_path: str, backend_url: str, provider: AIProvider) -> bool:
    """Write shared scripts + the provider's native hook config. Idempotent.

    Returns True if any file changed. Claude is handled by the existing
    ``repo_setup.install_claude_hooks`` and must not reach here.
    """
    repo = Path(repo_path)
    changed = _write_shared_scripts(repo, backend_url)
    if provider == AIProvider.codex:
        changed |= _write_json_if_changed(repo / ".codex" / "hooks.json", _codex_hooks_config())
    elif provider == AIProvider.copilot:
        changed |= _write_json_if_changed(
            repo / ".github" / "hooks" / "copilot-cli-policy.json", _copilot_hooks_config()
        )
    logger.info("agent_hooks_installed", repo=repo_path, provider=provider.value, changed=changed)
    return changed


def write_agent_mcp_config(repo_path: str, backend_url: str, provider: AIProvider) -> bool:
    """Copy the bridge + write the provider's MCP config. Idempotent."""
    repo = Path(repo_path)
    _copy_mcp_bridge(repo)
    if provider == AIProvider.codex:
        changed = _write_codex_config_toml(repo, backend_url)
    elif provider == AIProvider.copilot:
        changed = _write_json_if_changed(
            repo / ".github" / "copilot" / "mcp-config.json", _mcp_json_config(backend_url)
        )
    else:
        changed = False
    logger.info("agent_mcp_written", repo=repo_path, provider=provider.value, changed=changed)
    return changed


def append_agent_instructions(repo_path: str, provider: AIProvider) -> bool:
    """Write/replace the bodhiorchard section in ``AGENTS.md``. Idempotent.

    Both Codex and Copilot read ``AGENTS.md`` for repo instructions. Uses the
    same ``<!-- bodhiorchard:start/end -->`` markers as the CLAUDE.md path so
    re-runs replace the block in place rather than appending duplicates.
    """
    section = _agents_md_section()
    path = Path(repo_path) / "AGENTS.md"
    existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    if _BG_START in existing and _BG_END in existing:
        before = existing.split(_BG_START)[0]
        after = existing.split(_BG_END, 1)[1]
        updated = f"{before}{section.strip()}{after}"
    elif existing.strip():
        updated = f"{existing.rstrip()}\n\n{section}"
    else:
        updated = f"# AGENTS.md\n\n{section}"
    if updated.strip() == existing.strip():
        return False
    path.write_text(updated, encoding="utf-8")
    logger.info("agent_instructions_written", repo=repo_path, provider=provider.value)
    return True
