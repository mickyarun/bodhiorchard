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

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.handler_utils import require_non_empty
from app.mcp.synth_feature_writer import persist_synth_feature
from app.models.organization import Organization
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
