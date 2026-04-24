# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Regression: stderr must be drained concurrently with stdout.

The old code opened ``stderr=PIPE`` but only read stderr after the
process exited. If the child wrote more than ~64 KB to stderr (the OS
pipe buffer size on macOS) it would block on ``write()``, which stopped
stdout production, which stalled the stream-json reader, which sat there
until the 10-minute timeout fired. ``atoa_pax`` hit exactly this.

This test drives :func:`run_claude_code`'s internal subprocess via a
monkeypatch that swaps the ``claude`` binary for a tiny Python script
that blasts 200 KB to stderr while emitting minimal stdout, and asserts
the call completes quickly instead of timing out.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from app.services import claude_runner

# A tiny Python program that pretends to be ``claude`` for the purposes
# of this test: writes 200 KB to stderr, emits a single stream-json
# ``result`` success event to stdout, then exits 0. If stderr drain is
# broken, the process blocks on the first 64 KB chunk.
_FAKE_CLAUDE = """
import sys
sys.stderr.write('x' * 200_000)
sys.stderr.flush()
sys.stdout.write(
    '{"type":"result","subtype":"success","is_error":false,'
    '"result":"ok","num_turns":1,"total_cost_usd":0.0}\\n'
)
sys.stdout.flush()
"""


@pytest.mark.asyncio
async def test_heavy_stderr_does_not_deadlock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = tmp_path / "fake_claude.py"
    fake.write_text(_FAKE_CLAUDE)

    # Intercept CLI discovery so run_claude_code believes ``claude`` exists.
    monkeypatch.setattr(claude_runner, "is_claude_cli_available", lambda: True)
    original_create = asyncio.create_subprocess_exec

    async def fake_create(*cmd, **kwargs):  # type: ignore[no-untyped-def]
        # Replace just the first argument (the "claude" binary) with our
        # fake-interpreter invocation; preserve every other kwarg so the
        # real pipe / buffer / limit configuration is exercised.
        new_cmd = (sys.executable, str(fake), *cmd[1:])
        return await original_create(*new_cmd, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    # 10-second timeout is plenty for the fake; if stderr drain is broken
    # the old code would hang the full 10 seconds then error.
    result = await asyncio.wait_for(
        claude_runner.run_claude_code(
            prompt="ignored",
            working_dir=str(tmp_path),
            config=claude_runner.ClaudeRunnerConfig(
                max_turns=1,
                timeout_seconds=10,
                output_format="stream-json",
            ),
            progress_callback=lambda _: None,
        ),
        timeout=15,
    )

    assert result.success, f"CLI deadlocked on heavy stderr: {result.error!r}"
    assert result.output == "ok"
