# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Prepares the per-repo entries consumed by the global FEATURE_SYNTHESIS phase.

After each repo finishes its per-repo stripe, the orchestrator needs a
decision: "does this repo have work for the synthesis queue, and if so
what shape?". There are three shapes:

- ``None``  — skip this repo in B2 (incremental scan, GitNexus failed,
  Claude CLI absent, or no source files discovered).
- Cluster-fed — GitNexus produced clusters; this module pushes them
  onto the in-memory ``synthesis_queue`` keyed by ``(org_id, repo_name)``
  so the B2 MCP tool ``get_pending_features`` can dequeue them.
- Direct-scan — GitNexus found no clusters (tiny or unusual repo); the
  file listing is returned so Claude can walk it directly.

The resulting dict is appended to ``_pending_synthesis`` in the
orchestrator and fed into ``phase_b2_synthesis`` unchanged.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import structlog

from app.services.claude_runner import is_claude_cli_available
from app.services.scan_phases import _list_repo_files

logger = structlog.get_logger(__name__)


# Cluster-size thresholds. Small repos (< 10 clusters) let 2-file
# clusters through so we don't starve synthesis; larger repos require
# ≥3 files to filter noise.
_SYNTHESIS_MIN_FILES_SMALL = 2
_SYNTHESIS_MIN_FILES_LARGE = 3
_SYNTHESIS_SMALL_CLUSTER_THRESHOLD = 10
_SYNTHESIS_CLUSTER_FILE_CAP = 15


async def build_pending_synthesis(
    *,
    repo_name: str,
    repo_path: str,
    repo_id: uuid.UUID | None,
    org_id: uuid.UUID,
    is_incremental: bool,
    gitnexus_success: bool,
    gitnexus_features: list[Any],
    gitnexus_overview: str,
) -> dict[str, Any] | None:
    """Return a ``_pending_synthesis`` entry for this repo, or ``None``.

    Returns ``None`` when the repo should be skipped in B2 (incremental
    mode, GitNexus failed, Claude CLI absent, no tracked repo row, or
    no source files found in the direct-scan fallback). Async because
    the direct-scan fallback walks the directory tree via ``asyncio.to_thread``.

    ``repo_id`` must be non-None for any repo that might participate in
    synthesis: ``synthesized_features.repo_id`` is NOT NULL, and B2's
    queue self-heal (§D.2) looks up done clusters by ``repo_id``. An
    untracked repo is therefore silently skipped.
    """
    if is_incremental:
        return None
    if not gitnexus_success:
        return None
    if repo_id is None:
        logger.info("feature_synthesis_skipped_untracked_repo", repo_name=repo_name)
        return None
    if not is_claude_cli_available():
        logger.info("feature_synthesis_skipped_no_claude_cli")
        return None

    if gitnexus_features:
        from app.mcp.synthesis_queue import set_synthesis_queue

        total_clusters = len(gitnexus_features)
        min_files = (
            _SYNTHESIS_MIN_FILES_SMALL
            if total_clusters < _SYNTHESIS_SMALL_CLUSTER_THRESHOLD
            else _SYNTHESIS_MIN_FILES_LARGE
        )
        queue_items = [
            {
                "name": f.name,
                "files": f.files[:_SYNTHESIS_CLUSTER_FILE_CAP],
                "symbols": len(f.files),
                "repo_name": repo_name,
            }
            for f in gitnexus_features
            if len(f.files) >= min_files
        ]
        queue_key = set_synthesis_queue(str(org_id), queue_items, repo_name=repo_name)
        return {
            "repo_name": repo_name,
            "repo_path": repo_path,
            "repo_id": repo_id,
            "overview": gitnexus_overview,
            "queue_key": queue_key,
            "cluster_count": len(queue_items),
        }

    # Direct-scan fallback: no clusters, Claude walks the file tree.
    # Off-thread because ``_list_repo_files`` does synchronous disk I/O.
    files = await asyncio.to_thread(_list_repo_files, Path(repo_path))
    if not files:
        return None
    return {
        "repo_name": repo_name,
        "repo_path": repo_path,
        "repo_id": repo_id,
        "overview": gitnexus_overview,
        "queue_key": None,
        "cluster_count": 0,
        "direct_scan": True,
        "file_tree": "\n".join(files),
    }
