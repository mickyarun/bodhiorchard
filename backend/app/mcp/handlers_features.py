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

"""MCP handlers for the unified ``features`` table + bug search.

Replaces ``handlers_knowledge`` after the legacy ``knowledge_items``
table was retired in favour of ``features`` + ``feature_to_repo``.

Tools exposed (registered in :mod:`app.mcp.server`):

* ``get_features``           — semantic search across active features.
* ``check_feature_exists``   — duplicate-feature heuristic for the LLM.
* ``search_bugs``            — bug semantic search (unchanged).
* ``get_pending_features``   — synthesis queue head (unchanged).
* ``write_feature_registry`` — accumulate one synthesised feature for
  the reconciler (unchanged signature plus a required
  ``cluster_signature`` field).

Feature-content formatting and inline embedding live in
``app/services/feature_content.py`` so non-MCP callers can share them.
"""

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.handler_utils import require_non_empty
from app.mcp.synth_feature_writer import persist_synth_feature
from app.mcp.synthesis_queue import get_queue_remaining, remove_from_queue
from app.models.organization import Organization
from app.repositories.bug import BugRepository
from app.repositories.feature_reads import FeatureReadRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.services.embedding_service import embedding_service
from app.services.feature_content import format_feature_content
from app.services.feature_content import try_embed as _try_embed

logger = structlog.get_logger(__name__)

# Re-export for legacy callers (``handlers_scan`` imports these names).
__all__ = ["format_feature_content", "_try_embed"]


async def handle_get_features(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Hybrid keyword + semantic search over active features.

    Strategy chosen so the MCP path behaves predictably for both
    short title-like queries AND multi-word natural-language queries
    LLMs tend to produce:

    1. **Title-substring (ILIKE) first** — mirrors the frontend
       ``/v1/features?q=`` page exactly. High precision; alphabetical.
    2. **Semantic embedding fallback** — when the literal phrase
       isn't in any title, embed the query and rank by cosine
       distance against ``Feature.embedding``. Catches LLM phrasing
       like "payment links notes post-payment edit" that no title
       contains verbatim.

    Required: ``query`` (non-empty). Optional: ``limit`` (default 10,
    max 50), ``offset`` (default 0). The two backends share the same
    pagination semantics so the caller doesn't see which one fired
    except via the ``search_mode`` field in the response.

    Each result carries ``id`` so an LLM can put real feature UUIDs
    into the trailing ``{"linked_feature_ids": [...]}`` JSON fence
    the BUD section editor parses on save.
    """
    query = params.get("query", "")
    limit = min(int(params.get("limit", 10) or 10), 50)
    offset = max(int(params.get("offset", 0) or 0), 0)

    if not query or not query.strip():
        return {"results": [], "error": "query is required"}

    reads = FeatureReadRepository(db, org_id=org.id)

    # 1. Title-substring path first — same shape as the frontend.
    # Fetch limit+1 to detect has_more without a separate COUNT.
    rows = await reads.keyword_search(query, limit=limit + 1, offset=offset, only_active=True)
    search_mode = "keyword"

    # 2. Semantic fallback when keyword found nothing AT ALL (offset=0
    # check — don't fall back mid-pagination, that would confuse the
    # client about which page it's on). LLM queries like "payment
    # link notes post-payment edit" land here.
    if not rows and offset == 0:
        try:
            vector = await embedding_service.embed(query)
            semantic_rows = await reads.semantic_search(
                vector, limit=limit + 1, offset=0, only_active=True
            )
            rows = [feature for feature, _distance in semantic_rows]
            search_mode = "semantic"
        except Exception:
            logger.exception("mcp_get_features_semantic_fallback_failed", query=query[:100])
            # Leave rows as the empty keyword result — caller still
            # sees zero results, just no semantic enrichment.

    has_more = len(rows) > limit
    rows = rows[:limit]

    return {
        "results": [
            {
                "id": str(feature.id),
                "title": feature.feature_title,
                "description": feature.description,
                "capabilities": list((feature.capabilities or {}).get("capabilities", [])),
                "tags": list(feature.tags or []),
                "source": feature.source,
                "source_ref": feature.source_ref,
                "feature_status": feature.feature_status or "implemented",
            }
            for feature in rows
        ],
        "search_mode": search_mode,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "next_offset": offset + limit if has_more else None,
    }


async def handle_search_bugs(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Search bugs by description using semantic search."""
    query = params.get("query", "")
    bug_status = params.get("status", "open")
    limit = min(params.get("limit", 10), 50)

    bug_repo = BugRepository(db, org_id=org.id)
    bugs = await bug_repo.search_by_status(status_filter=bug_status, limit=limit)

    logger.info("mcp_search_bugs", org_id=str(org.id), query=query[:100], found=len(bugs))
    return {
        "bugs": [
            {
                "id": str(bug.id),
                "title": bug.title,
                "description": (bug.description or "")[:1000],
                "severity": bug.severity.value if bug.severity else "medium",
                "status": bug.status.value if bug.status else "open",
                "module": bug.module,
            }
            for bug in bugs
        ],
    }


async def handle_get_pending_features(
    db: AsyncSession,  # noqa: ARG001 — uses the in-memory queue
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Return the next batch of clusters awaiting feature synthesis."""
    batch_size = min(params.get("batch_size", 5), 10)
    remaining = get_queue_remaining(str(org.id))
    batch = remaining[:batch_size]
    return {
        "clusters": batch,
        "remaining_count": len(remaining),
        "batch_size": len(batch),
        "done": len(remaining) == 0,
    }


async def handle_write_feature_registry(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Accumulate one synthesised feature for end-of-batch reconciliation.

    Per-LLM-tool-call invocation: the writer appends a ``FeatureWrite``
    to the per-repo accumulator; the synthesise scan stage drains it
    at end-of-batch and reconciles against the existing active set
    (signature → Jaccard → cosine match).

    ``cluster_signature`` is required — it is the reconciler's
    primary identity key. The synthesise stage looks up each
    cluster's signature from ``cluster_cache`` before invoking the
    LLM, so the model does not have to compute it itself.
    """
    error = require_non_empty(
        params,
        "feature_name",
        "description",
        "capabilities",
        "tags",
        "cluster_signature",
    )
    if error:
        return error

    feature_name = params["feature_name"]
    repo_name = params.get("repo_name")
    source_clusters = params.get("source_clusters", [])
    title = f"Feature: {feature_name}"

    if not repo_name:
        return {
            "success": False,
            "error": (
                "repo_name is required so the synth row can be bound to a tracked repository."
            ),
        }

    tr_repo = TrackedRepoRepository(db, org_id=org.id)
    tracked = await tr_repo.get_by_name(repo_name)
    if tracked is None:
        return {
            "success": False,
            "error": (
                f"Unknown repo_name: {repo_name!r}. Call the tool again with "
                "one of the org's active tracked repository names."
            ),
        }
    repo_id = tracked.id

    queued = await persist_synth_feature(
        db=db,
        org=org,
        repo_id=repo_id,
        feature_title=title,
        description=params["description"],
        capabilities=params["capabilities"],
        cluster_names=source_clusters,
        cluster_signature=params["cluster_signature"],
        code_locations=params.get("code_locations"),
        tags=list(params.get("tags") or []),
        head_sha=params.get("head_sha"),
        source_ref=params.get("source_ref"),
    )

    if source_clusters:
        remove_from_queue(str(org.id), source_clusters)

    remaining = len(get_queue_remaining(str(org.id)))
    logger.info(
        "mcp_write_feature_registry",
        org_id=str(org.id),
        title=title,
        repo=repo_name,
        queued_in_batch=queued,
        remaining=remaining,
    )
    return {
        "success": True,
        "title": title,
        "queued_in_batch": queued,
        "remaining_clusters": remaining,
    }


async def handle_check_feature_exists(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Check if a similar feature already exists via semantic search."""
    query = params["feature_description"]
    threshold = params.get("threshold", 0.6)

    try:
        vector = await embedding_service.embed(query)
    except Exception:
        logger.exception("check_feature_embed_failed", query=query[:100])
        return {"exists": False, "feature_count": 0, "features": [], "error": "Embedding failed"}

    reads = FeatureReadRepository(db, org_id=org.id)
    rows = await reads.semantic_search(vector, limit=5, only_active=True)

    features: list[dict[str, Any]] = []
    for feature, distance in rows:
        score = round(1.0 - distance, 4)
        if score < threshold:
            continue
        features.append(
            {
                "title": feature.feature_title,
                "description": feature.description,
                "score": score,
                "match_strength": "strong" if score >= 0.85 else "partial",
                "feature_status": feature.feature_status or "implemented",
                "source_ref": feature.source_ref,
            }
        )

    return {
        "exists": len(features) > 0,
        "feature_count": len(features),
        "features": features,
    }
