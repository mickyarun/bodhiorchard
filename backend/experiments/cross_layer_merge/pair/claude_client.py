# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Subprocess wrapper around the ``claude`` CLI for the sandbox verifier.

Production uses ``services/claude_runner.py`` (with MCP). The sandbox
deliberately uses a much simpler one-shot call: the prompt carries
all candidates inline so a single CLI turn produces the JSON answer.
This trades MCP fidelity for prompt-iteration speed; promotion to
production swaps in the real runner.
"""

import asyncio
import json
import re
import subprocess
from typing import Any, cast

# Per project_claude_subprocess_isolation memo: forces default output style so
# learning-mode "★ Insight" markers don't leak into JSON we have to parse.
CLAUDE_SETTINGS_FLAG = '--settings={"outputStyle":"default"}'

CLAUDE_TIMEOUT_SECONDS = 90

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}", re.MULTILINE)


def _run_claude_blocking(prompt: str) -> str:
    """Synchronous CLI invocation. Wrapped via ``asyncio.to_thread`` below."""
    completed = subprocess.run(
        [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "text",
            CLAUDE_SETTINGS_FLAG,
        ],
        capture_output=True,
        text=True,
        timeout=CLAUDE_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"claude exited {completed.returncode}: {completed.stderr}")
    return completed.stdout


async def ask_claude(prompt: str) -> str:
    """Run the prompt through ``claude`` and return raw stdout text."""
    return await asyncio.to_thread(_run_claude_blocking, prompt)


def parse_verdict(response_text: str) -> dict[str, Any]:
    """Pull the first JSON object out of Claude's text response and validate."""
    match = _JSON_BLOCK.search(response_text)
    if not match:
        raise ValueError(f"no JSON block in response: {response_text!r}")
    obj = json.loads(match.group(0))
    action = obj.get("action")
    if action not in ("merge", "no_match"):
        raise ValueError(f"unexpected action in verdict: {obj!r}")
    if action == "merge" and ("canonical_synth_id" not in obj or "absorb_synth_ids" not in obj):
        raise ValueError(f"merge verdict missing required fields: {obj!r}")
    return cast(dict[str, Any], obj)
