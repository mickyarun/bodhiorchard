# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""MCP handlers exclusive to the v2 scan pipeline.

The single tool is ``write_synthesis_feature`` — Claude calls it once
per feature it produces during the synthesize stage. The handler is
**staging-only**: it appends an immutable row to ``synthesized_features``
and nothing else. The merge phase (Stage B3) is the sole writer of
canonical ``knowledge_items`` rows.

This mirrors the legacy ``write_feature_registry`` refactor — keeping
the responsibility split clean: synthesis stages new features, merge
promotes them. With both v1 and v2 staging-only, the merge phase sees
unmerged synth rows on one side and existing canonicals from prior
scans on the other, instead of duplicate inputs from "feature already
written by synthesis".
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.handler_utils import require_non_empty
from app.mcp.synth_feature_writer import persist_synth_feature
from app.models.organization import Organization
from app.repositories.cluster_cache import ClusterCacheRepository
from app.repositories.tracked_repository import TrackedRepoRepository

logger = structlog.get_logger(__name__)


async def handle_write_synthesis_feature(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Stage one v2-synthesised feature into ``synthesized_features``.

    Required params: ``name``, ``description``, ``source_community_ids``
    (non-empty list of community_id strings — the ids you saw in the
    prompt's JSON payload), ``repo_name``.

    Optional: ``dropped_community_ids``, ``capabilities``, ``code_locations``,
    ``tags``, ``scan_id``, ``repo_id``. ``scan_id`` and ``repo_id`` come
    from the synthesis prompt's *Scan context* block — when supplied,
    they bind the persisted feature to that exact scan run instead of
    relying on a server-side active-scan lookup.
    """
    error = require_non_empty(params, "name", "description", "source_community_ids", "repo_name")
    if error:
        return error

    repo_name = params["repo_name"]
    feature_name = params["name"]
    title = f"Feature: {feature_name}"
    description: str = params["description"]
    source_ids: list[str] = list(params.get("source_community_ids") or [])
    dropped_ids: list[str] = list(params.get("dropped_community_ids") or [])
    capabilities: list[str] = list(params.get("capabilities") or [])
    tags: list[str] = list(params.get("tags") or [])
    code_locations = params.get("code_locations")

    explicit_scan_id = _parse_uuid_or_log(params.get("scan_id"), field="scan_id")
    explicit_repo_id = _parse_uuid_or_log(params.get("repo_id"), field="repo_id")

    # Prefer the explicit repo_id from the prompt over the name lookup —
    # it survives renames mid-scan and saves a query. Fall back to
    # name resolution when the LLM omitted it.
    if explicit_repo_id is not None:
        if not await _repo_belongs_to_org(db, org_id=org.id, repo_id=explicit_repo_id):
            return _unknown_repo_error(repo_name)
        repo_id: uuid.UUID | None = explicit_repo_id
    else:
        repo_id = await _resolve_repo_id(db, org_id=org.id, repo_name=repo_name)
    if repo_id is None:
        return _unknown_repo_error(repo_name)

    # Auto-expand ``code_locations`` with every file from every cluster
    # the LLM listed in ``source_community_ids``. The synthesis prompt
    # passes back the underlying ``cluster_ids`` (e.g. ``c22``, ``c39``)
    # so we can look them up in ``cluster_cache`` and union the files.
    # This closes the gap where Claude lists only a handful of
    # representative files per feature, leaving the rest of the
    # cluster's files unreferenced and surfaced as "uncovered" by the
    # post-synthesis audit.
    code_locations = await _expand_code_locations(
        db,
        org_id=org.id,
        repo_id=repo_id,
        source_ids=source_ids,
        existing=code_locations,
    )

    # Stage-only: write the immutable per-scan audit row with
    # ``knowledge_item_id=None``. The merge phase (B3) reads these rows,
    # creates the canonical KI, and back-fills ``knowledge_item_id`` on
    # the synth row in the same transaction.
    synth_row = await persist_synth_feature(
        db=db,
        org=org,
        repo_id=repo_id,
        feature_title=title,
        description=description,
        capabilities=capabilities,
        cluster_names=source_ids,
        code_locations=code_locations,
        tags=tags,
        knowledge_item_id=None,
        scan_id=explicit_scan_id,
    )

    # Flush so NOT-NULL / FK violations on the synth row surface before
    # the dispatcher's auto-commit instead of getting swallowed.
    await db.flush()

    if synth_row is None:
        logger.error(
            "scan_synth_feature_not_persisted",
            org_id=str(org.id),
            repo=repo_name,
            title=title,
            hint=(
                "persist_synth_feature returned None — likely no active Scan "
                "row for this org. Check the most-recent log line "
                "'synth_feature_skipped_no_active_scan' for context."
            ),
        )

    logger.info(
        "scan_write_synthesis_feature",
        org_id=str(org.id),
        repo=repo_name,
        title=title,
        source_count=len(source_ids),
        dropped_count=len(dropped_ids),
        synth_row_id=str(synth_row.id) if synth_row else None,
        synth_persisted=synth_row is not None,
    )
    return {
        "success": True,
        "title": title,
        "source_count": len(source_ids),
        "dropped_count": len(dropped_ids),
        "synth_row_id": str(synth_row.id) if synth_row else None,
        "synth_persisted": synth_row is not None,
    }


# --- helpers --------------------------------------------------------


_CLUSTER_ID_RE = re.compile(r"^c\d+$")
"""Cluster id format emitted by ``code_indexer.seed.stable_cluster_id``."""

# Path heuristics for layer assignment when expanded files land outside
# Claude's existing layer buckets. Same regexes as ``coverage_audit``.
_FRONTEND_EXT_RE = re.compile(r"\.(vue|svelte|astro|tsx|jsx)$")
_FRONTEND_DIRS_RE = re.compile(r"/(views|pages|components|composables|stores|layouts)/")
_BATCH_DIRS_RE = re.compile(r"/(cron|jobs?|workers|batch|queue|tasks?|schedule)/")


async def _expand_code_locations(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    source_ids: list[str],
    existing: Any,
) -> dict[str, list[str]]:
    """Union files from every cluster in ``source_ids`` into ``existing``.

    The prompt instructs the LLM to put cluster_cache row ids
    (``c<N>``) in ``source_community_ids``. We look those up, fetch
    their full file lists, and merge into ``existing`` keyed by layer.

    Strings that don't match the ``c<N>`` pattern are ignored — they're
    likely composite labels (``"merchant + payments + invoice"``) from
    older synthesis prompts. Mixed input is handled gracefully:
    cluster_ids get expanded, labels get ignored, and the existing
    ``code_locations`` is returned untouched if no cluster_ids are
    found.
    """
    base: dict[str, list[str]] = {}
    if isinstance(existing, dict):
        for layer, files in existing.items():
            if not isinstance(layer, str) or not isinstance(files, list):
                continue
            base[layer] = [f for f in files if isinstance(f, str)]

    candidate_ids = [s for s in source_ids if isinstance(s, str) and _CLUSTER_ID_RE.match(s)]
    if not candidate_ids:
        return base

    head_sha = await _latest_head_sha(db, org_id=org_id, repo_id=repo_id)
    if not head_sha:
        return base

    cc_repo = ClusterCacheRepository(db, org_id=org_id)
    cached_rows = await cc_repo.list_for_repo_sha(repo_id=repo_id, head_sha=head_sha)
    by_id = {row.cluster_id: row for row in cached_rows}

    seen: set[str] = {f for layer_files in base.values() for f in layer_files}
    layered: dict[str, list[str]] = defaultdict(list, {k: list(v) for k, v in base.items()})

    for cid in candidate_ids:
        cluster = by_id.get(cid)
        if cluster is None:
            continue
        for f in cluster.files or []:
            if not isinstance(f, str) or f in seen:
                continue
            seen.add(f)
            layered[_classify_layer(f)].append(f)

    return dict(layered)


def _classify_layer(path: str) -> str:
    """Map a file path to ``frontend`` / ``batch`` / ``backend`` by heuristic."""
    if _FRONTEND_EXT_RE.search(path) or _FRONTEND_DIRS_RE.search(path):
        return "frontend"
    if _BATCH_DIRS_RE.search(path):
        return "batch"
    return "backend"


async def _latest_head_sha(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> str | None:
    """Resolve the head_sha for cluster_cache lookup.

    Reads from ``tracked_repositories.head_sha`` first (set by the
    persist phase at scan completion); falls back to whatever's most
    recent in ``cluster_cache`` so mid-scan synthesis writes still
    auto-expand against the current scan's cache rows.
    """
    tracked = await TrackedRepoRepository(db, org_id=org_id).get_by_id(repo_id)
    if tracked is not None and tracked.head_sha:
        return tracked.head_sha
    return await ClusterCacheRepository(db, org_id=org_id).latest_head_sha(repo_id=repo_id)


async def _resolve_repo_id(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    repo_name: str,
) -> uuid.UUID | None:
    """Look up the tracked repo's UUID by name (org-scoped)."""
    tracked = await TrackedRepoRepository(db, org_id=org_id).get_by_name(repo_name)
    return tracked.id if tracked is not None else None


async def _repo_belongs_to_org(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> bool:
    """Confirm a prompt-supplied repo_id is tracked by this org."""
    tracked = await TrackedRepoRepository(db, org_id=org_id).get_by_id(repo_id)
    return tracked is not None


def _parse_uuid_or_log(value: Any, *, field: str) -> uuid.UUID | None:
    """Coerce a tool-arg string to UUID. Logs and returns None on garbage."""
    if value in (None, ""):
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        logger.warning("write_synthesis_feature_invalid_uuid", field=field, value=str(value)[:64])
        return None


def _unknown_repo_error(repo_name: str) -> dict[str, Any]:
    return {
        "success": False,
        "error": (
            f"Unknown repo_name: {repo_name!r}. Call the tool again with one "
            "of the org's active tracked repository names."
        ),
    }
