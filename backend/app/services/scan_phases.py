# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Legacy phase-function module — being decomposed into ``app.scan.*``.

Each phase used to live here. As part of the stabilisation plan we're
moving them one at a time to ``app.scan.per_repo`` / ``app.scan.global_``
modules so each file stays under the 300-line review gate. This module
re-exports the moved names so existing imports (``scan_pipeline``,
``scan_repo_loop``) keep working without a churn-heavy rename across
unrelated call sites. New code should import from the package directly.
"""

from typing import Any

import structlog

from app.scan.global_.feature_merge import _list_repo_files, phase_b3_merge
from app.scan.global_.feature_synthesis import phase_b2_synthesis
from app.scan.global_.persist_results import phase_g_persist
from app.scan.global_.skill_remap import phase_e2_skill_remap
from app.scan.per_repo.mode_detection import phase_a_scan_mode
from app.scan.per_repo.repo_setup import phase_b1_repo_setup
from app.scan.per_repo.skill_extraction import phase_e_skills
from app.services.claude_runner import (
    ProgressCallback,
)

logger = structlog.get_logger(__name__)

# Phases moved to ``app.scan`` are re-exported here so legacy callers
# keep working. New code should import from the package directly:
#   from app.scan.per_repo.mode_detection import phase_a_scan_mode
__all__ = [
    "_list_repo_files",  # legacy re-export for scan_synthesis_queue
    "make_scan_progress_logger",
    "phase_a_scan_mode",
    "phase_b1_repo_setup",
    "phase_b2_synthesis",
    "phase_b3_merge",
    "phase_e2_skill_remap",
    "phase_e_skills",
    "phase_g_persist",
]


def make_scan_progress_logger(
    *,
    scan_id: str,
    phase: str,
    repo_name: str | None = None,
) -> ProgressCallback:
    """Build a ``ProgressCallback`` that logs every Claude tool_use event.

    Without this, the merge subprocess can spend ten minutes calling
    ``merge_features`` and the only thing on disk is the start/end
    metadata. Mid-run state (which titles are being merged into which)
    is invisible until the DB audit reads ``synthesized_features`` after
    the fact.

    Pattern matches ``app.services.job_chat.make_progress_callback`` and
    siblings — same shape, scan-specific topic so log filtering can
    target one scan via ``grep '"event": "claude_tool_call"'``.
    """

    def _on_tool(tool: str, _tool_input: dict[str, Any]) -> None:
        # ``_tool_input`` is part of the ``ProgressCallback`` signature
        # contract but the audit log only needs the tool name. Keeping
        # the second parameter (with the underscore prefix) makes
        # mypy / ruff happy without a # noqa suppression.
        logger.info(
            "claude_tool_call",
            scan_id=scan_id,
            phase=phase,
            repo=repo_name,
            tool=tool,
        )

    return _on_tool
