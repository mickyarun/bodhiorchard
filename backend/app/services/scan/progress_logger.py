# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Progress callback that logs every Claude ``tool_use`` event during a scan.

The merge / synthesis subprocesses can spend several minutes calling MCP
tools; without this audit log the only thing on disk is the start/end
metadata, so mid-run state (which titles are being merged into which)
would be invisible until the DB audit reads the table after the fact.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.services.claude_runner import ProgressCallback

logger = structlog.get_logger(__name__)


def make_scan_progress_logger(
    *,
    scan_id: str,
    phase: str,
    repo_name: str | None = None,
) -> ProgressCallback:
    """Build a ``ProgressCallback`` that logs every Claude tool_use event.

    Same shape as ``app.services.job_chat.make_progress_callback`` and
    siblings — scan-specific topic so log filtering can target one scan
    via ``grep '"event": "claude_tool_call"'``.
    """

    def _on_tool(tool: str, _tool_input: dict[str, Any]) -> None:
        # ``_tool_input`` is part of the ``ProgressCallback`` signature
        # contract but the audit log only needs the tool name.
        logger.info(
            "claude_tool_call",
            scan_id=scan_id,
            phase=phase,
            repo=repo_name,
            tool=tool,
        )

    return _on_tool
