# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Tests for ``bud_agent_retry.maybe_retry_on_git_auth_failure``.

Pins the orchestration contract that the BUD agent handler depends on:
when does retry fire, what does it call, and with what side effects.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import bud_agent_retry
from app.services.claude_runner import ClaudeRunnerConfig, ClaudeRunResult

AUTH_FAIL_OUTPUT = "remote: Invalid username or token. Password authentication is not supported."


def _success_result(output: str) -> ClaudeRunResult:
    return ClaudeRunResult(success=True, output=output, cost_usd=0.01, turns_used=2)


def _base_config() -> ClaudeRunnerConfig:
    return ClaudeRunnerConfig(max_turns=5, timeout_seconds=60)


def _common_kwargs() -> dict[str, object]:
    return {
        "prompt": "review this",
        "spawn_cwd": "/clone/octocat-hello",
        "working_dir": "/clone/octocat-hello",
        "config": _base_config(),
        "progress_callback": None,
        "org_id": uuid.uuid4(),
        "bud_id": uuid.uuid4(),
        "task_id": uuid.uuid4(),
        "skill_id": uuid.uuid4(),
        "skill_slug": "code-reviewer",
        "repo_id": uuid.uuid4(),
        "db": MagicMock(),
    }


@pytest.fixture(autouse=True)
def _patch_dependencies():  # type: ignore[no-untyped-def]
    """Stub the side-effecting calls so each test asserts wiring, not behaviour."""
    with (
        patch.object(bud_agent_retry, "invalidate_installation_token") as inv,
        patch.object(
            bud_agent_retry, "refresh_origin_token", new=AsyncMock(return_value=True)
        ) as refresh,
        patch.object(bud_agent_retry, "log_agent_activity", new=AsyncMock()) as logact,
        patch.object(
            bud_agent_retry, "run_claude_code", new=AsyncMock(return_value=_success_result("{}"))
        ) as rcc,
        patch.object(bud_agent_retry, "mint_session_id", return_value=uuid.UUID(int=42)) as mint,
    ):
        yield {
            "invalidate": inv,
            "refresh": refresh,
            "log_activity": logact,
            "run_claude_code": rcc,
            "mint_session_id": mint,
        }


async def test_no_retry_when_no_working_dir(_patch_dependencies) -> None:
    kwargs = _common_kwargs()
    kwargs["working_dir"] = None
    first = _success_result(AUTH_FAIL_OUTPUT)
    out = await bud_agent_retry.maybe_retry_on_git_auth_failure(result=first, **kwargs)  # type: ignore[arg-type]
    assert out is first
    _patch_dependencies["invalidate"].assert_not_called()
    _patch_dependencies["run_claude_code"].assert_not_called()


async def test_no_retry_when_first_spawn_crashed(_patch_dependencies) -> None:
    kwargs = _common_kwargs()
    crashed = ClaudeRunResult(success=False, output=AUTH_FAIL_OUTPUT, error="boom")
    out = await bud_agent_retry.maybe_retry_on_git_auth_failure(result=crashed, **kwargs)  # type: ignore[arg-type]
    assert out is crashed
    _patch_dependencies["invalidate"].assert_not_called()
    _patch_dependencies["run_claude_code"].assert_not_called()


async def test_no_retry_when_output_clean(_patch_dependencies) -> None:
    kwargs = _common_kwargs()
    clean = _success_result('{"code_review_comments": []}')
    out = await bud_agent_retry.maybe_retry_on_git_auth_failure(result=clean, **kwargs)  # type: ignore[arg-type]
    assert out is clean
    _patch_dependencies["invalidate"].assert_not_called()


async def test_retry_invalidates_refreshes_and_respawns(_patch_dependencies) -> None:
    kwargs = _common_kwargs()
    first = _success_result(AUTH_FAIL_OUTPUT)

    out = await bud_agent_retry.maybe_retry_on_git_auth_failure(result=first, **kwargs)  # type: ignore[arg-type]

    # Token cache dropped first — otherwise the re-stamp would write the
    # same rejected token back into ``origin``.
    _patch_dependencies["invalidate"].assert_called_once_with(str(kwargs["org_id"]))
    _patch_dependencies["refresh"].assert_awaited_once()
    # Activity row recorded so the BUD timeline shows both spawns.
    _patch_dependencies["log_activity"].assert_awaited_once()
    assert _patch_dependencies["log_activity"].await_args.kwargs["event_type"] == "agent_retried"
    # Second spawn fired with a FRESH session id (not None, not the
    # original) so the CLI doesn't replay partial MCP side-effects.
    rcc = _patch_dependencies["run_claude_code"]
    rcc.assert_awaited_once()
    retry_config = rcc.await_args.kwargs["config"]
    assert retry_config.cli_session_id == str(uuid.UUID(int=42))
    assert retry_config.is_resume is False
    # Return value is the SECOND spawn's result, not the first.
    assert out.output == "{}"


async def test_retry_preserves_mcp_and_tool_allowlist(_patch_dependencies) -> None:
    kwargs = _common_kwargs()
    base = _base_config()
    base.allowed_tools = ["Bash", "Read"]
    kwargs["config"] = base
    first = _success_result(AUTH_FAIL_OUTPUT)

    await bud_agent_retry.maybe_retry_on_git_auth_failure(result=first, **kwargs)  # type: ignore[arg-type]

    retry_config = _patch_dependencies["run_claude_code"].await_args.kwargs["config"]
    # Tool allowlist + MCP must carry through — the retry is the same
    # skill running in the same scope, only the session id changes.
    assert retry_config.allowed_tools == ["Bash", "Read"]
    assert retry_config.max_turns == base.max_turns
    assert retry_config.timeout_seconds == base.timeout_seconds
