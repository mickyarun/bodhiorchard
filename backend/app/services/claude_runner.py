# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Claude Code CLI runner for executing AI tasks locally.

This module provides the interface for triggering Claude Code from the
Bodhiorchard backend via local subprocess execution.
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from app.services.gitnexus_utils import find_npx as _find_npx

logger = structlog.get_logger(__name__)

ProgressCallback = Callable[[str, dict[str, Any]], None]  # (tool_name, tool_input)

_BRIDGE_PATH = str(Path(__file__).resolve().parent.parent / "mcp" / "stdio_bridge.py")


@dataclass
class ClaudeRunResult:
    """Result from a Claude Code CLI execution."""

    success: bool
    output: str
    cost_usd: float | None = None
    turns_used: int | None = None
    duration_ms: int | None = None
    error: str | None = None


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server to expose to the Claude CLI.

    Generates a stdio-based MCP config that spawns the Bodhiorchard bridge script,
    which translates MCP JSON-RPC calls into REST API calls back to the
    running Bodhiorchard backend.
    """

    backend_url: str
    mcp_token: str
    tool_names: list[str] = field(default_factory=list)


@dataclass
class ClaudeRunnerConfig:
    """Configuration for the Claude Code runner."""

    max_turns: int = 20
    timeout_seconds: int = 300
    output_format: str = "json"
    mcp: MCPServerConfig | None = None
    system_prompt_files: list[str] = field(default_factory=list)
    model: str | None = None
    effort: str | None = None
    env_extra: dict[str, str] | None = None


def _find_tool_uses(obj: Any, callback: ProgressCallback) -> None:
    """Recursively search a parsed JSON object for tool_use blocks.

    Walks dicts and lists looking for ``{"type": "tool_use", "name": "..."}``.
    Format-agnostic — works regardless of nesting depth in the stream event.
    """
    if isinstance(obj, dict):
        if obj.get("type") == "tool_use" and isinstance(obj.get("name"), str):
            callback(obj["name"], obj.get("input") or {})
        for v in obj.values():
            _find_tool_uses(v, callback)
    elif isinstance(obj, list):
        for item in obj:
            _find_tool_uses(item, callback)


async def _run_with_streaming(
    cmd: list[str],
    cwd: str,
    timeout: int,
    progress_callback: ProgressCallback,
    *,
    env: dict[str, str] | None = None,
) -> ClaudeRunResult:
    """Run Claude CLI with stream-json output, emitting progress on each tool call.

    Reads stdout line-by-line, parses JSON events, and calls
    ``progress_callback`` whenever a tool_use block is found.
    Captures the final ``result`` event for the return value.

    Uses asyncio.create_subprocess_exec (NOT shell) — safe from injection.
    """
    result_text = ""
    cost: float | None = None
    turns: int | None = None
    error_subtype: str | None = None
    # Pre-bind so the ``CancelledError`` / ``TimeoutError`` branches can
    # reference ``proc`` even if cancellation fires before the subprocess
    # is actually spawned.
    proc: asyncio.subprocess.Process | None = None

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=10 * 1024 * 1024,  # 10MB — Claude stream-json lines can exceed 64KB default
        )

        async def _read_and_wait() -> None:
            nonlocal result_text, cost, turns, error_subtype
            assert proc.stdout is not None  # noqa: S101
            while True:
                try:
                    line = await proc.stdout.readline()
                except ValueError:
                    # Line exceeded even the 10MB buffer — stop parsing but let process finish
                    logger.warning("claude_stream_line_overflow", limit_mb=10)
                    break
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    event = json.loads(text)
                except json.JSONDecodeError:
                    continue

                # Look for tool_use blocks anywhere in the event
                _find_tool_uses(event, progress_callback)

                # Capture the final result event
                if isinstance(event, dict) and event.get("type") == "result":
                    result_text = event.get("result", "") or ""
                    cost = event.get("total_cost_usd")
                    turns = event.get("num_turns")
                    subtype = event.get("subtype", "")
                    if isinstance(subtype, str) and subtype.startswith("error"):
                        error_subtype = subtype

            # Wait for process exit under the same timeout
            await proc.wait()

        await asyncio.wait_for(_read_and_wait(), timeout=timeout)
    except TimeoutError:
        if proc is not None:
            try:
                proc.kill()
                await proc.wait()
                logger.info("claude_subprocess_killed_on_timeout", pid=proc.pid)
            except ProcessLookupError:
                pass
        return ClaudeRunResult(
            success=False,
            output="",
            error=f"Timed out after {timeout}s",
        )
    except asyncio.CancelledError:
        # Caller cancelled the job — kill the CLI so it stops making
        # MCP tool calls (and spending tokens) before we re-raise.
        if proc is not None:
            try:
                proc.kill()
                await proc.wait()
                logger.info("claude_subprocess_killed_on_cancel", pid=proc.pid)
            except ProcessLookupError:
                pass
        raise
    except FileNotFoundError:
        return ClaudeRunResult(
            success=False,
            output="",
            error="Claude CLI binary not found",
        )

    # Read any remaining stderr
    stderr_bytes = await proc.stderr.read() if proc.stderr else b""
    stderr_str = stderr_bytes.decode("utf-8", errors="replace")

    logger.info(
        "claude_stream_finished",
        returncode=proc.returncode,
        output_length=len(result_text),
        stderr_length=len(stderr_str),
        stderr_preview=stderr_str[:300] if stderr_str else "",
    )

    if proc.returncode != 0:
        logger.error(
            "claude_run_failed",
            returncode=proc.returncode,
            stderr=stderr_str[:500],
        )
        return ClaudeRunResult(
            success=False,
            output=result_text,
            error=f"Exit code {proc.returncode}: {stderr_str[:500]}",
        )

    if error_subtype:
        logger.warning(
            "claude_run_error_subtype",
            subtype=error_subtype,
            turns=turns,
            cost_usd=cost,
        )
        return ClaudeRunResult(
            success=False,
            output=result_text,
            cost_usd=cost,
            turns_used=turns,
            error=f"Claude CLI: {error_subtype} after {turns} turns",
        )

    logger.info(
        "claude_run_complete",
        cost_usd=cost,
        turns=turns,
        output_length=len(result_text),
        output_preview=result_text[:200],
    )

    return ClaudeRunResult(
        success=True,
        output=result_text,
        cost_usd=cost,
        turns_used=turns,
    )


def is_claude_cli_available() -> bool:
    """Check if the 'claude' CLI tool is installed and accessible.

    Returns:
        True if the claude binary is found on PATH.
    """
    return shutil.which("claude") is not None


async def run_claude_code(
    prompt: str,
    working_dir: str | Path | None = None,
    config: ClaudeRunnerConfig | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ClaudeRunResult:
    """Run a prompt via the Claude Code CLI using subprocess.

    Uses asyncio.create_subprocess_exec (NOT shell) for safety — no shell
    injection possible since arguments are passed as a list, never
    interpolated into a shell string.

    Args:
        prompt: The prompt/instruction to send to Claude Code.
        working_dir: Directory to run in (for codebase context). Defaults to cwd.
        config: Runner configuration (turns, timeout).
        progress_callback: Optional callback invoked with each tool name as
            Claude uses tools. When provided, forces ``stream-json`` output
            format for real-time updates. When ``None``, uses the batch path.

    Returns:
        ClaudeRunResult with output or error details.
    """
    if config is None:
        config = ClaudeRunnerConfig()

    if not is_claude_cli_available():
        return ClaudeRunResult(
            success=False,
            output="",
            error=(
                "Claude CLI not found. Install: curl -fsSL https://claude.ai/install.sh | bash"
            ),
        )

    cwd = str(working_dir) if working_dir else "."

    # Force stream-json when a progress callback is provided
    output_format = config.output_format
    if progress_callback is not None:
        output_format = "stream-json"

    # Build command as a list — safe from shell injection
    # (uses asyncio.create_subprocess_exec, NOT shell=True)
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        output_format,
        "--dangerously-skip-permissions",
        # Force a neutral output style so skill output isn't polluted by the
        # developer's interactive outputStyle (e.g. "learning" prepends
        # ★ Insight blocks that break HTML/JSON extraction downstream).
        "--settings",
        json.dumps({"outputStyle": "default"}),
    ]

    # stream-json requires --verbose (Claude CLI constraint)
    if output_format == "stream-json":
        cmd.append("--verbose")

    # 0 means unlimited — omit the flag so Claude uses its default (no cap)
    if config.max_turns > 0:
        cmd.extend(["--max-turns", str(config.max_turns)])

    if config.model:
        cmd.extend(["--model", config.model])
    if config.effort:
        cmd.extend(["--effort", config.effort])

    # Append system prompt files (e.g., design system reference)
    for spf in config.system_prompt_files:
        cmd.extend(["--append-system-prompt-file", spf])

    # Write temporary MCP config if tools are needed
    mcp_config_file = None
    if config.mcp:
        bridge_path = str(Path(__file__).resolve().parent.parent / "mcp" / "stdio_bridge.py")
        mcp_json = {
            "mcpServers": {
                "bodhiorchard": {
                    "command": sys.executable,
                    "args": [bridge_path],
                    "env": {
                        "BODHIORCHARD_BACKEND_URL": config.mcp.backend_url,
                        "BODHIORCHARD_MCP_TOKEN": config.mcp.mcp_token,
                        "BODHIORCHARD_MCP_TOKEN_FILE": "",
                        "BODHIORCHARD_MCP_TOOLS": ",".join(config.mcp.tool_names),
                    },
                },
            },
        }
        with tempfile.NamedTemporaryFile(
            suffix=".json",
            prefix="bodhiorchard_mcp_",
            delete=False,
            mode="w",
        ) as tmp:
            tmp.write(json.dumps(mcp_json))
            mcp_config_file = Path(tmp.name)
        cmd.extend(["--mcp-config", str(mcp_config_file)])

    logger.info(
        "claude_run_start",
        cmd=cmd,
        prompt_preview=prompt[:100],
        cwd=cwd,
        max_turns=config.max_turns,
        timeout_seconds=config.timeout_seconds,
        output_format=output_format,
        mcp_enabled=config.mcp is not None,
    )

    # Build subprocess environment with optional extras (e.g. agent context)
    sub_env: dict[str, str] | None = None
    if config.env_extra:
        sub_env = {**os.environ, **config.env_extra}

    # Streaming path: read stdout line-by-line for live progress
    if progress_callback is not None:
        try:
            return await _run_with_streaming(
                cmd, cwd, config.timeout_seconds, progress_callback, env=sub_env,
            )
        finally:
            if mcp_config_file is not None:
                mcp_config_file.unlink(missing_ok=True)

    # Batch path: wait for full output (existing behavior)
    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env=sub_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=config.timeout_seconds,
        )

        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")

        logger.info(
            "claude_subprocess_finished",
            returncode=proc.returncode,
            stdout_length=len(stdout_str),
            stderr_length=len(stderr_str),
            stdout_preview=stdout_str[:500],
            stderr_preview=stderr_str[:300] if stderr_str else "",
        )

        if proc.returncode != 0:
            logger.error(
                "claude_run_failed",
                returncode=proc.returncode,
                stderr=stderr_str[:500],
            )
            return ClaudeRunResult(
                success=False,
                output=stdout_str,
                error=f"Exit code {proc.returncode}: {stderr_str[:500]}",
            )

        # Parse JSON output from Claude Code CLI
        result_text = stdout_str
        cost = None
        turns = None

        if config.output_format == "json":
            try:
                parsed = json.loads(stdout_str)
                subtype = parsed.get("subtype", "") if isinstance(parsed, dict) else ""
                logger.info(
                    "claude_json_parsed",
                    keys=list(parsed.keys()) if isinstance(parsed, dict) else "not_a_dict",
                    type_field=parsed.get("type") if isinstance(parsed, dict) else None,
                    subtype=subtype,
                )
                result_text = parsed.get("result", "") or ""
                cost = parsed.get("total_cost_usd")
                turns = parsed.get("num_turns")

                # Detect error subtypes (e.g. error_max_turns)
                if isinstance(subtype, str) and subtype.startswith("error"):
                    logger.warning(
                        "claude_run_error_subtype",
                        subtype=subtype,
                        turns=turns,
                        cost_usd=cost,
                    )
                    return ClaudeRunResult(
                        success=False,
                        output=result_text,
                        cost_usd=cost,
                        turns_used=turns,
                        error=f"Claude CLI: {subtype} after {turns} turns",
                    )
            except json.JSONDecodeError:
                logger.warning(
                    "claude_json_parse_failed",
                    stdout_preview=stdout_str[:300],
                )
                result_text = stdout_str

        logger.info(
            "claude_run_complete",
            cost_usd=cost,
            turns=turns,
            output_length=len(result_text),
            output_preview=result_text[:200],
        )

        return ClaudeRunResult(
            success=True,
            output=result_text,
            cost_usd=cost,
            turns_used=turns,
        )

    except TimeoutError:
        # Kill the subprocess so it stops making MCP tool calls
        # before the caller revokes the token
        if proc is not None:
            try:
                proc.kill()
                await proc.wait()
                logger.info("claude_subprocess_killed_on_timeout", pid=proc.pid)
            except ProcessLookupError:
                pass  # Already exited
        logger.error("claude_run_timeout", timeout=config.timeout_seconds)
        return ClaudeRunResult(
            success=False,
            output="",
            error=f"Timed out after {config.timeout_seconds}s",
        )
    except asyncio.CancelledError:
        if proc is not None:
            try:
                proc.kill()
                await proc.wait()
                logger.info("claude_subprocess_killed_on_cancel", pid=proc.pid)
            except ProcessLookupError:
                pass
        raise
    except FileNotFoundError:
        return ClaudeRunResult(
            success=False,
            output="",
            error="Claude CLI binary not found",
        )
    finally:
        if mcp_config_file is not None:
            mcp_config_file.unlink(missing_ok=True)


async def ensure_gitnexus_mcp() -> None:
    """Register GitNexus MCP server with Claude Code (idempotent).

    Uses ``claude mcp add`` to register the GitNexus stdio MCP server
    globally, so all subsequent Claude CLI runs can query indexed repos
    for UI components, layouts, and code structure during design generation.
    """
    npx = _find_npx()
    if not npx:
        logger.debug("gitnexus_mcp_skip_no_npx")
        return

    # Check if already registered
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "mcp",
            "list",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if "gitnexus" in stdout.decode():
            return
    except (TimeoutError, FileNotFoundError, OSError):
        return  # CLI not available — skip silently

    # Register: claude mcp add gitnexus -s user -- npx --yes gitnexus mcp
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "mcp",
            "add",
            "gitnexus",
            "-s",
            "user",
            "--",
            npx,
            "--yes",
            "gitnexus",
            "mcp",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=15)
        logger.info("gitnexus_mcp_registered", npx=npx)
    except (TimeoutError, FileNotFoundError, OSError) as exc:
        logger.warning("gitnexus_mcp_register_failed", error=str(exc))


async def _get_claude_version() -> str | None:
    """Run ``claude --version`` and return the version string, or None on failure.

    This is a fast, offline check that confirms the binary actually executes
    (beyond just existing on PATH).  Uses create_subprocess_exec (no shell).
    """
    claude_path = shutil.which("claude")
    if claude_path is None:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            claude_path,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0:
            return stdout.decode("utf-8", errors="replace").strip()[:100]
    except (TimeoutError, FileNotFoundError, OSError):
        pass
    return None


async def test_claude_connection(
    env_extra: dict[str, str] | None = None,
) -> dict:
    """Run a simple test to verify Claude Code CLI works.

    Performs two checks:
    1. ``claude --version`` — fast, offline, confirms binary is runnable.
    2. A trivial prompt — confirms the API key is valid and the CLI can
       reach the Anthropic API.  Uses a 90-second timeout to accommodate
       first-invocation cold starts.

    Args:
        env_extra: Optional env overlay passed through to the subprocess
            (e.g. a provisional ``ANTHROPIC_API_KEY`` the user is
            validating in the setup wizard). Preferred over mutating
            ``os.environ`` because concurrent agent runs share that.

    Returns:
        A dict with test results: cli_available, cli_version, test_passed,
        output, error.
    """
    version = await _get_claude_version()

    result: dict[str, object] = {
        "cli_available": version is not None,
        "cli_version": version,
        "test_passed": False,
        "output": "",
        "error": None,
    }

    if not result["cli_available"]:
        result["error"] = (
            "Claude CLI not installed. Run: curl -fsSL https://claude.ai/install.sh | bash"
        )
        return result

    logger.info("claude_connection_test_start", cli_version=version)

    test_result = await run_claude_code(
        prompt="Reply with exactly: BODHIORCHARD_CONNECTION_OK",
        config=ClaudeRunnerConfig(
            max_turns=1, timeout_seconds=90, env_extra=env_extra,
        ),
    )

    result["test_passed"] = test_result.success
    result["output"] = test_result.output[:200]
    result["error"] = test_result.error
    result["cost_usd"] = test_result.cost_usd

    logger.info(
        "claude_connection_test_result",
        test_passed=result["test_passed"],
        output_preview=str(result["output"])[:100],
        error=result["error"],
    )

    return result
