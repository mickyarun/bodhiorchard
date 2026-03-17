"""Claude Code CLI runner for executing AI tasks locally.

This module provides the interface for triggering Claude Code from the
FlowDev backend via local subprocess execution.
"""

import asyncio
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


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
class ClaudeRunnerConfig:
    """Configuration for the Claude Code runner."""

    max_turns: int = 20
    max_budget_usd: float = 2.0
    timeout_seconds: int = 300
    output_format: str = "json"


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
) -> ClaudeRunResult:
    """Run a prompt via the Claude Code CLI using subprocess.

    Uses asyncio.create_subprocess_exec (NOT shell) for safety — no shell
    injection possible since arguments are passed as a list, never
    interpolated into a shell string.

    Args:
        prompt: The prompt/instruction to send to Claude Code.
        working_dir: Directory to run in (for codebase context). Defaults to cwd.
        config: Runner configuration (turns, budget, timeout).

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

    # Build command as a list — safe from shell injection
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        config.output_format,
        "--max-turns",
        str(config.max_turns),
        "--dangerously-skip-permissions",
    ]

    logger.info(
        "claude_run_start",
        cmd=cmd,
        prompt_preview=prompt[:100],
        cwd=cwd,
        max_turns=config.max_turns,
        timeout_seconds=config.timeout_seconds,
        output_format=config.output_format,
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
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
                logger.info(
                    "claude_json_parsed",
                    keys=list(parsed.keys()) if isinstance(parsed, dict) else "not_a_dict",
                    type_field=parsed.get("type") if isinstance(parsed, dict) else None,
                )
                result_text = parsed.get("result", stdout_str)
                cost = parsed.get("total_cost_usd")
                turns = parsed.get("num_turns")
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
        logger.error("claude_run_timeout", timeout=config.timeout_seconds)
        return ClaudeRunResult(
            success=False,
            output="",
            error=f"Timed out after {config.timeout_seconds}s",
        )
    except FileNotFoundError:
        return ClaudeRunResult(
            success=False,
            output="",
            error="Claude CLI binary not found",
        )


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


async def test_claude_connection() -> dict:
    """Run a simple test to verify Claude Code CLI works.

    Performs two checks:
    1. ``claude --version`` — fast, offline, confirms binary is runnable.
    2. A trivial prompt — confirms the API key is valid and the CLI can
       reach the Anthropic API.  Uses a 90-second timeout to accommodate
       first-invocation cold starts.

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
        prompt="Reply with exactly: FLOWDEV_CONNECTION_OK",
        config=ClaudeRunnerConfig(max_turns=1, max_budget_usd=0.10, timeout_seconds=90),
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
