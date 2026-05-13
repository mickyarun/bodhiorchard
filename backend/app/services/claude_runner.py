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

"""Claude Code CLI runner for executing AI tasks locally.

This module provides the interface for triggering Claude Code from the
Bodhiorchard backend via local subprocess execution.
"""

import asyncio
import contextlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from app.services import claude_errors
from app.services.claude_errors import ClaudeErrorCode
from app.services.claude_guard import (
    apply_subprocess_rlimits,
    build_claude_env,
    build_inline_settings_json,
    maybe_wrap_with_sandbox,
)

logger = structlog.get_logger(__name__)

ProgressCallback = Callable[[str, dict[str, Any]], None]  # (tool_name, tool_input)

# Absolute path to the MCP stdio bridge script — passed to the Claude CLI
# via ``--mcp-config`` so the bridge subprocess can be launched with the
# correct interpreter regardless of caller cwd.
_BRIDGE_PATH = str(Path(__file__).resolve().parent.parent / "mcp" / "stdio_bridge.py")


@dataclass
class ClaudeRunResult:
    """Result from a Claude Code CLI execution.

    ``error_code`` is a stable identifier for the failure category — the
    frontend uses it to render rich UI (settings deep-links, role-aware
    CTAs). It is ``None`` on success and on legacy code paths that don't
    flow through ``claude_errors``; ``error`` remains the human-readable
    fallback for any caller that doesn't translate the code itself.
    """

    success: bool
    output: str
    cost_usd: float | None = None
    turns_used: int | None = None
    duration_ms: int | None = None
    error: str | None = None
    error_code: ClaudeErrorCode | None = None
    # Prompt-cache telemetry from the CLI's ``result`` event ``usage`` block.
    # ``cache_read_input_tokens`` should dominate in steady-state iteration;
    # ``cache_creation_input_tokens`` is the cost of seeding the cache and
    # should fall to ~0 on warm sessions. See claude_runner._extract_usage.
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None


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
    # Session-id wiring for keeping the Anthropic prompt cache warm across
    # CLI invocations. The CLI assigns its own UUID by default, so an
    # externally-tracked id (e.g. our chat thread's session_id) would not
    # match its persistence file. Two flags solve this:
    #   - ``--session-id <uuid>`` on the FIRST call forces the CLI to use
    #     OUR uuid as the session id (writes ``~/.claude/projects/.../<uuid>.jsonl``).
    #   - ``--resume <uuid>`` on subsequent calls loads that same session
    #     from disk, keeping the prompt cache warm (5-min Anthropic TTL).
    # ``is_resume`` selects which flag to pass. Both flags use the same id
    # so the caller owns the namespace. Leaving ``cli_session_id`` None
    # uses the CLI default behaviour (fresh session each run).
    cli_session_id: str | None = None
    is_resume: bool = False
    # Restrict the subprocess to a specific tool allowlist. When non-empty,
    # passes ``--allowedTools <comma list>`` to the Claude CLI so the
    # subprocess can ONLY invoke those tools. Anything else (Bash, Read,
    # Edit, ToolSearch, ...) is denied. Use for narrowly-scoped phases
    # like the global merge that should only emit one MCP tool.
    allowed_tools: list[str] = field(default_factory=list)


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
    cache_read: int | None = None
    cache_creation: int | None = None
    error_subtype: str | None = None
    # Structured error surfaced by any event (not just ``result``). The CLI
    # can emit ``is_error: true`` payloads on auth / credit / rate-limit /
    # argv-too-long failures and then exit non-zero without ever sending a
    # ``result`` event — in which case the only signal to the user would
    # otherwise be "Exit code 1:" with empty stderr.
    event_error_message: str | None = None
    # Last few raw stdout lines kept as a diagnostic fallback when every
    # structured path has failed.
    recent_lines: list[str] = []
    # stderr drained concurrently so the OS pipe buffer never fills up
    # and stalls the CLI. Classic asyncio subprocess deadlock.
    stderr_chunks: list[bytes] = []
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
            # guard: kernel-enforced RLIMIT_AS + RLIMIT_NPROC + setsid
            # in the child. Returns ``None`` on Windows so this is a no-op there.
            preexec_fn=apply_subprocess_rlimits(),
        )

        async def _drain_stderr() -> None:
            """Continuously drain stderr so the OS pipe buffer never fills.

            Without this, writing more than ~64 KB to stderr blocks the
            subprocess, which stops stdout, which stalls the stream-json
            reader, which sits there until the 10-minute timeout fires.
            Seen in the wild when the Claude CLI's ``--verbose`` flag
            emits hook / MCP startup logs on real repos.
            """
            assert proc.stderr is not None  # noqa: S101
            while True:
                try:
                    chunk = await proc.stderr.read(65536)
                except ValueError:
                    continue
                if not chunk:
                    break
                if sum(len(c) for c in stderr_chunks) < 1_000_000:
                    stderr_chunks.append(chunk)

        async def _read_and_wait() -> None:
            nonlocal result_text, cost, turns, cache_read, cache_creation
            nonlocal error_subtype, event_error_message
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
                # Keep a rolling tail of raw lines as a diagnostic fallback.
                recent_lines.append(text)
                if len(recent_lines) > 20:
                    recent_lines.pop(0)
                try:
                    event = json.loads(text)
                except json.JSONDecodeError:
                    continue

                # Look for tool_use blocks anywhere in the event
                _find_tool_uses(event, progress_callback)

                # Structured error anywhere in the stream — the CLI sends
                # ``is_error: true`` on auth / credit / rate-limit failures
                # without necessarily wrapping them in a ``result`` event.
                if event_error_message is None and isinstance(event, dict):
                    extracted = _extract_event_error(event)
                    if extracted:
                        event_error_message = extracted

                # Capture the final result event
                if isinstance(event, dict) and event.get("type") == "result":
                    result_text = event.get("result", "") or ""
                    cost = event.get("total_cost_usd")
                    turns = event.get("num_turns")
                    cache_read, cache_creation = _extract_cache_usage(event)
                    subtype = event.get("subtype", "")
                    if isinstance(subtype, str) and subtype.startswith("error"):
                        error_subtype = subtype

            # Wait for process exit under the same timeout
            await proc.wait()

        await asyncio.wait_for(
            asyncio.gather(_read_and_wait(), _drain_stderr()),
            timeout=timeout,
        )
    except TimeoutError:
        if proc is not None:
            try:
                proc.kill()
                await proc.wait()
                logger.info("claude_subprocess_killed_on_timeout", pid=proc.pid)
            except ProcessLookupError:
                # Race: subprocess already exited between the kill and the
                # wait. Nothing to clean up — fall through to the diagnostic
                # path below.
                pass
        # Include whatever diagnostic signal we did capture before the
        # timeout — a timed-out CLI usually still produced *some* output,
        # and knowing the last line often points at the real hang.
        stderr_preview = b"".join(stderr_chunks).decode("utf-8", errors="replace")[:300]
        last_stdout = recent_lines[-1][:200] if recent_lines else ""
        logger.error(
            "claude_run_timeout",
            timeout=timeout,
            last_stdout=last_stdout,
            stderr_preview=stderr_preview,
        )
        code, message = claude_errors.from_timeout(timeout)
        diagnostic_suffix = ""
        if last_stdout:
            diagnostic_suffix = f" (last stdout: {last_stdout})"
        elif stderr_preview:
            diagnostic_suffix = f" (stderr: {stderr_preview[:200]})"
        return ClaudeRunResult(
            success=False,
            output="",
            error=message + diagnostic_suffix,
            error_code=code,
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
                # Race: subprocess already exited before we got the cancel
                # signal. Swallow and propagate the original cancellation.
                pass
        raise
    except FileNotFoundError:
        code, message = claude_errors.from_binary_missing()
        return ClaudeRunResult(
            success=False,
            output="",
            error=message,
            error_code=code,
        )

    # stderr was drained concurrently (above) so the pipe never blocked.
    stderr_bytes = b"".join(stderr_chunks)
    stderr_str = stderr_bytes.decode("utf-8", errors="replace")

    logger.info(
        "claude_stream_finished",
        returncode=proc.returncode,
        output_length=len(result_text),
        stderr_length=len(stderr_str),
        stderr_preview=stderr_str[:300] if stderr_str else "",
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_creation,
    )

    if proc.returncode != 0:
        # Prefer, in order: structured error from any event; error_subtype
        # on the final result event; stderr; last raw stdout lines. The
        # last-line fallback is ugly but vastly more useful than nothing
        # when every structured path has failed.
        detail = event_error_message
        if not detail and error_subtype:
            detail = f"{error_subtype} after {turns or 0} turns"
        if not detail and stderr_str:
            detail = stderr_str[:500]
        if not detail and recent_lines:
            detail = "last CLI output: " + " | ".join(recent_lines[-3:])[:500]
        logger.error(
            "claude_run_failed",
            returncode=proc.returncode,
            stderr=stderr_str[:500],
            event_error=event_error_message,
            error_subtype=error_subtype,
            recent_lines=recent_lines[-5:],
        )
        code, message = claude_errors.from_returncode(proc.returncode or 0, detail)
        return ClaudeRunResult(
            success=False,
            output=result_text,
            error=message,
            error_code=code,
        )

    if error_subtype:
        logger.warning(
            "claude_run_error_subtype",
            subtype=error_subtype,
            turns=turns,
            cost_usd=cost,
        )
        code, message = claude_errors.from_subtype(error_subtype, turns=turns)
        return ClaudeRunResult(
            success=False,
            output=result_text,
            cost_usd=cost,
            turns_used=turns,
            error=message,
            error_code=code,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_creation,
        )

    logger.info(
        "claude_run_complete",
        cost_usd=cost,
        turns=turns,
        output_length=len(result_text),
        output_preview=result_text[:200],
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_creation,
    )

    return ClaudeRunResult(
        success=True,
        output=result_text,
        cost_usd=cost,
        turns_used=turns,
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_creation,
    )


def is_claude_cli_available() -> bool:
    """Check if the 'claude' CLI tool is installed and accessible.

    Returns:
        True if the claude binary is found on PATH.
    """
    return shutil.which("claude") is not None


# Path prefixes the spawn cwd MUST start with. A positive allowlist:
# any working_dir that does not begin with one of these roots is
# rejected by string comparison BEFORE any filesystem syscall touches
# the value. The list covers macOS user homes, Linux user homes, the
# standard tmp dirs used by tests + pytest, and the canonical Full
# Docker clone root. Operators with a custom layout can extend at
# deploy time via ``BODHIORCHARD_EXTRA_CWD_ROOTS`` (colon-separated,
# each entry MUST end with ``/``).
_ALLOWED_CWD_ROOTS: tuple[str, ...] = (
    "/Users/",
    "/home/",
    "/root/",
    "/tmp/",
    "/var/tmp/",
    "/var/folders/",
    "/private/var/",
    "/workspace/",
    "/data/repos/",
    "/app/",
)


def _allowed_cwd_roots() -> tuple[str, ...]:
    """Return the in-tree allowlist plus any deploy-time additions."""
    extra = os.environ.get("BODHIORCHARD_EXTRA_CWD_ROOTS", "")
    if not extra:
        return _ALLOWED_CWD_ROOTS
    extras = tuple(p for p in extra.split(":") if p.endswith("/"))
    return _ALLOWED_CWD_ROOTS + extras


# Suffix characters allowed AFTER the constant root prefix. ``..`` and
# absolute-path injection are excluded by construction since a leading
# slash isn't permitted. This regex is the canonical structural
# sanitizer for CodeQL's ``py/path-injection`` taint query — the path
# string is reconstructed from a hardcoded prefix + a regex-validated
# suffix, breaking the taint flow before it reaches ``Path()``.
_SAFE_SUFFIX_RE = re.compile(r"^[A-Za-z0-9_\-./+= ]*$")


def _validate_working_dir(working_dir: str | Path | None) -> str:
    """Resolve and validate the spawn cwd. Returns absolute path.

    Three-step structural sanitization:

    1. Match the input against one of the constant prefixes in
       ``_allowed_cwd_roots()``. Reject if none match.
    2. Regex-validate the remaining suffix (alphanumerics, dash, dot,
       slash, underscore, plus, equals, space). No ``..``, no other
       shell-meta characters.
    3. Reconstruct the path string from the matched constant prefix
       plus the validated suffix. CodeQL's ``py/path-injection`` query
       recognizes this reconstruct-from-constant pattern as a sanitizer.
    4. Reject credential dirs (``.ssh``, ``.aws``, ...) on the
       reconstructed string. Then resolve and check ``is_dir()``.

    ``None`` falls back to the FastAPI worker's own cwd, which is trusted.
    """
    if working_dir is None:
        return str(Path.cwd().resolve())

    raw = str(working_dir)

    matched_root: str | None = None
    for root in _allowed_cwd_roots():
        if raw.startswith(root):
            matched_root = root
            break
    if matched_root is None:
        raise ValueError(f"run_claude_code working_dir not under an allowed root: {raw!r}")

    suffix = raw[len(matched_root) :]
    if not _SAFE_SUFFIX_RE.match(suffix):
        raise ValueError(
            f"run_claude_code working_dir suffix contains disallowed characters: {raw!r}"
        )

    # Reconstruct from constant prefix + sanitized suffix. The result
    # is no longer derived from a tainted source by CodeQL's flow rules.
    safe = matched_root + suffix

    for cred in ("/.ssh", "/.aws", "/.gnupg", "/.kube", "/.claude/.credentials"):
        if cred in safe:
            raise ValueError(f"run_claude_code refuses to spawn inside a credential dir: {safe!r}")

    resolved = Path(safe).resolve()
    if not resolved.is_dir():
        raise ValueError(
            f"run_claude_code working_dir does not exist or is not a directory: {resolved}"
        )

    return str(resolved)


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

    # Resolve to an absolute path so the ``--add-dir`` workspace pin workspace
    # pin allows exactly the intended directory. With a relative ``"."``
    # the CLI would widen the filesystem allowlist to whatever the
    # FastAPI worker happens to be running from.
    #
    # ``working_dir`` is set by trusted internal backend code (job_design,
    # bud_agent_handler, scan/synthesis) and never flows from raw HTTP
    # request bodies. We still validate strictly: the resolved path must
    # be an existing directory and must NOT alias a credential or system
    # root, so even a buggy caller can't widen the sandbox.
    cwd = _validate_working_dir(working_dir)

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
        # Inline ``--settings`` JSON. Built from a security-aware
        # builder so we get, in one place:
        # * outputStyle "default" — neutralizes the developer's
        #   interactive outputStyle (e.g. "learning" would inject
        #   ★ Insight blocks that break downstream extraction);
        # * permissions.deny — declarative deny list for known-bad
        #   bash patterns and secret-file paths;
        # * disableBypassPermissionsMode — hard-disable YOLO inside the
        #   child so a planted .claude/settings.json cannot re-enable it;
        # * hooks.PreToolUse — wires the regex-based ``pretool_guard.py``
        #   script as the real Bash / Read gate.
        "--settings",
        build_inline_settings_json(),
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
    if config.cli_session_id:
        # First call in a thread uses --session-id to claim the namespace;
        # subsequent calls use --resume to load the prior session and hit
        # the prompt cache. Same uuid in both flags.
        flag = "--resume" if config.is_resume else "--session-id"
        cmd.extend([flag, config.cli_session_id])
    if config.allowed_tools:
        # Tighten the subprocess sandbox: only the listed tools can be
        # invoked. Used by the merge phase to disallow Bash / Read /
        # ToolSearch and force Claude to emit ``apply_feature_merge_plan``
        # ops instead of exploring the codebase.
        cmd.extend(["--allowedTools", ",".join(config.allowed_tools)])

    # guard: pin Claude's filesystem allowlist to the working
    # directory. Without this, a successful prompt-injection can
    # ``Read(~/.ssh/id_rsa)`` even though the working directory is the
    # cloned repo. ``--add-dir`` is additive; the CLI's default working-dir
    # entry stays in place so legitimate repo reads continue to work.
    cmd.extend(["--add-dir", cwd])

    # Append system prompt files (e.g., design system reference)
    for spf in config.system_prompt_files:
        cmd.extend(["--append-system-prompt-file", spf])

    # Write temporary MCP config if tools are needed
    mcp_config_file = None
    if config.mcp:
        mcp_json = {
            "mcpServers": {
                "bodhiorchard": {
                    "command": sys.executable,
                    "args": [_BRIDGE_PATH],
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
            # guard: tighten file mode to owner-read-only BEFORE
            # writing the token, so there is no window where the token is
            # on disk under a world-readable umask. Best-effort on Windows
            # (no ``fchmod``); the path-based ``os.chmod`` below covers it.
            with contextlib.suppress(OSError):
                os.fchmod(tmp.fileno(), 0o600)
            tmp.write(json.dumps(mcp_json))
            mcp_config_file = Path(tmp.name)
        with contextlib.suppress(OSError):
            os.chmod(mcp_config_file, 0o600)
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

    # guard: build the subprocess env from a whitelist instead of
    # inheriting ``os.environ`` wholesale. Removes ``ENCRYPTION_KEY``,
    # ``DATABASE_URL``, ``SECRET_KEY``, ``GITHUB_TOKEN`` and friends from
    # the child's view so a prompt-injection that escapes the Bash deny
    # rules has nothing valuable to ``echo $...`` out.
    sub_env: dict[str, str] = build_claude_env(config.env_extra)

    # macOS Hybrid mode: optional macOS Seatbelt wrap. No-op on Linux /
    # Windows, or when BODHIORCHARD_HYBRID_SANDBOX env flag is unset.
    cmd = maybe_wrap_with_sandbox(cmd, cwd)

    # Streaming path: read stdout line-by-line for live progress
    if progress_callback is not None:
        try:
            return await _run_with_streaming(
                cmd,
                cwd,
                config.timeout_seconds,
                progress_callback,
                env=sub_env,
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
            # guard: same rlimits + setsid the streaming path uses.
            preexec_fn=apply_subprocess_rlimits(),
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
            # The CLI writes structured errors (auth, credit, rate-limit, model
            # deprecation) to stdout JSON with empty stderr. Surface that human
            # message instead of the opaque "Exit code N:".
            api_error = _parse_cli_error_payload(stdout_str)
            detail = api_error or (stderr_str[:500] if stderr_str else None)
            logger.error(
                "claude_run_failed",
                returncode=proc.returncode,
                stderr=stderr_str[:500],
                api_error=api_error,
            )
            code, message = claude_errors.from_returncode(proc.returncode or 0, detail)
            return ClaudeRunResult(
                success=False,
                output=stdout_str,
                error=message,
                error_code=code,
            )

        # Parse JSON output from Claude Code CLI
        result_text = stdout_str
        cost = None
        turns = None
        cache_read: int | None = None
        cache_creation: int | None = None

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
                if isinstance(parsed, dict):
                    cache_read, cache_creation = _extract_cache_usage(parsed)

                # Detect error subtypes (e.g. error_max_turns)
                if isinstance(subtype, str) and subtype.startswith("error"):
                    logger.warning(
                        "claude_run_error_subtype",
                        subtype=subtype,
                        turns=turns,
                        cost_usd=cost,
                    )
                    code, message = claude_errors.from_subtype(subtype, turns=turns)
                    return ClaudeRunResult(
                        success=False,
                        output=result_text,
                        cost_usd=cost,
                        turns_used=turns,
                        error=message,
                        error_code=code,
                        cache_read_tokens=cache_read,
                        cache_creation_tokens=cache_creation,
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
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_creation,
        )

        return ClaudeRunResult(
            success=True,
            output=result_text,
            cost_usd=cost,
            turns_used=turns,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_creation,
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
                # Race: subprocess already exited between the kill and the
                # wait. Nothing to clean up — fall through to the diagnostic
                # path below.
                pass  # Already exited
        logger.error("claude_run_timeout", timeout=config.timeout_seconds)
        code, message = claude_errors.from_timeout(config.timeout_seconds)
        return ClaudeRunResult(
            success=False,
            output="",
            error=message,
            error_code=code,
        )
    except asyncio.CancelledError:
        if proc is not None:
            try:
                proc.kill()
                await proc.wait()
                logger.info("claude_subprocess_killed_on_cancel", pid=proc.pid)
            except ProcessLookupError:
                # Race: subprocess already exited before we got the cancel
                # signal. Swallow and propagate the original cancellation.
                pass
        raise
    except FileNotFoundError:
        code, message = claude_errors.from_binary_missing()
        return ClaudeRunResult(
            success=False,
            output="",
            error=message,
            error_code=code,
        )
    finally:
        if mcp_config_file is not None:
            mcp_config_file.unlink(missing_ok=True)


def _extract_event_error(event: dict[str, Any]) -> str | None:
    """Pull a human error message out of a single stream-json event.

    The Claude CLI emits errors in several shapes depending on where the
    failure occurred (auth, credit, rate-limit, argv-too-long, subprocess
    crash in a plugin, …). This function normalizes them.

    Returns:
        A short human string, or ``None`` if no error was detectable in
        this event.
    """
    if not isinstance(event, dict):
        return None
    # Pattern 1: top-level {"is_error": true, "result": "...", "api_error_status": 429}
    if event.get("is_error"):
        msg = (event.get("result") or event.get("error") or "").strip()
        status = event.get("api_error_status")
        if msg and status:
            return f"{msg} (HTTP {status})"[:500]
        if msg:
            return msg[:500]
    # Pattern 2: {"type": "error", "message": "..."} or {"type": "error",
    # "error": {...}}
    if event.get("type") == "error":
        message = event.get("message")
        if isinstance(message, str) and message:
            return message[:500]
        err = event.get("error")
        if isinstance(err, dict):
            return (err.get("message") or err.get("type") or "unknown error")[:500]
        if isinstance(err, str):
            return err[:500]
    # Pattern 3: result event with subtype starting with "error_" often
    # carries a human blurb in ``result``.
    subtype = event.get("subtype")
    if isinstance(subtype, str) and subtype.startswith("error"):
        msg = (event.get("result") or "").strip()
        if msg:
            return f"{subtype}: {msg}"[:500]
    return None


def _extract_cache_usage(event: dict[str, Any]) -> tuple[int | None, int | None]:
    """Pull (cache_read_tokens, cache_creation_tokens) from a CLI result event.

    The Claude CLI puts the Anthropic API ``usage`` block under either
    ``usage`` at the top level (newer CLIs) or nested in ``message.usage``
    (older streaming events). We accept both shapes.

    A warm session (Anthropic prompt cache hit) shows
    ``cache_read_input_tokens > 0`` and ``cache_creation_input_tokens ~ 0``;
    a cold start is the opposite. Use these to verify ``--resume`` is
    actually buying us a cache hit.
    """
    usage = event.get("usage")
    if not isinstance(usage, dict):
        msg = event.get("message")
        if isinstance(msg, dict):
            usage = msg.get("usage")
    if not isinstance(usage, dict):
        return None, None
    read = _coerce_token_count(usage.get("cache_read_input_tokens"))
    creation = _coerce_token_count(usage.get("cache_creation_input_tokens"))
    # When the usage block is present but neither field parses, log once at
    # debug so a future CLI schema change doesn't silently null out cache
    # telemetry — the whole point of this helper is to verify --resume is
    # buying cache hits.
    if read is None and creation is None and usage:
        logger.debug("claude_usage_unparseable", usage_keys=sorted(usage.keys()))
    return read, creation


def _coerce_token_count(value: Any) -> int | None:
    """Coerce a usage-block token count to ``int``, accepting int or float.

    The CLI returns ints today; this is forward-compat with a JSON-number
    serialization that lands as ``float`` post-parse.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _parse_cli_error_payload(stdout_str: str) -> str | None:
    """Extract a human error message from a non-zero CLI run's stdout JSON.

    Returns ``None`` when stdout isn't a recognisable Claude CLI error envelope,
    so the caller can fall back to the generic exit-code message.
    """
    try:
        parsed = json.loads(stdout_str)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict) or not parsed.get("is_error"):
        return None
    msg = (parsed.get("result") or "").strip()
    status_code = parsed.get("api_error_status")
    if msg and status_code:
        return f"{msg} (HTTP {status_code})"
    return msg or None


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
            # guard: scrub env even for the offline ``--version``
            # check, so the version probe doesn't accidentally become a
            # disclosure surface (e.g. if a future CLI release logs
            # ``ANTHROPIC_API_KEY`` presence to stderr).
            env=build_claude_env(None),
            preexec_fn=apply_subprocess_rlimits(),
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0:
            return stdout.decode("utf-8", errors="replace").strip()[:100]
    except (TimeoutError, FileNotFoundError, OSError):
        # Best-effort offline version probe; any failure (no binary on
        # PATH, syscall error, slow startup) means "version unknown" —
        # which the caller treats as a soft signal, not a hard error.
        pass
    return None


async def test_claude_connection(
    env_extra: dict[str, str] | None = None,
) -> dict[str, Any]:
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
            max_turns=1,
            timeout_seconds=90,
            env_extra=env_extra,
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
