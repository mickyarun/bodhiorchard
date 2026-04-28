# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Data collection for the cross-repo feature merge prompt.

Splits the active feature set into two groups for the two-section
prompt (``EXISTING canonicals`` vs ``NEW features``), pulling the
right enrichment fields from the right table for each:

- NEW rows pull ``description`` / ``capabilities`` / ``code_locations``
  from ``synthesized_features`` (the immutable per-scan audit — freshest
  synthesis output for this scan).
- EXISTING rows pull ``summary`` from ``knowledge_items.content`` (the
  canonical merged view; may have been Claude-rewritten by prior merges).

Keeping this off ``feature_merge.py`` keeps the orchestrator focused on
the LLM call + post-merge audit. Both modules sit under ~200 lines.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.synthesized_feature import SynthesizedFeatureRepository


def pick_merge_model(
    feature_count: int,
    *,
    default_model: str,
    large_model: str,
) -> str:
    """Choose a merge model based on the active feature count.

    Sonnet is preferred for typical scale (≤ ``merge_sonnet_quality_budget``)
    where the two-section prompt fits well inside its 1M context;
    Opus escalates only when the run is large enough that the extra
    quality is worth the cost.

    Args:
        feature_count: Active feature count for this org.
        default_model: Resolved per-org default (e.g. Sonnet 4.6).
        large_model: Resolved per-org large-batch model (e.g. Opus 4.7).

    Returns:
        The model id to pass into ``ClaudeRunnerConfig(model=...)``.
    """
    if feature_count > settings.llm.merge_sonnet_quality_budget:
        return large_model
    return default_model


def _summary_first_sentence(content: str | None) -> str:
    """Extract a short summary line from a knowledge_item's content.

    The schema has no dedicated summary column; ``content`` is a
    Markdown-ish blob whose first paragraph is typically a 1-2 sentence
    description. Take up to the first period/newline so the prompt row
    stays lean (~60 tok).
    """
    if not content:
        return ""
    first_block = content.split("\n", 1)[0].strip()
    if not first_block:
        return ""
    # Trim at the first sentence boundary that produces a non-trivial line.
    end = first_block.find(". ")
    if end == -1:
        return first_block[:200]
    return first_block[: end + 1]


def _top_code_locations(code_locations: dict[str, Any] | None, limit: int = 2) -> list[str]:
    """Pick a small set of representative file paths from the synth row.

    ``synthesized_features.code_locations`` is a layer → list[path] map
    (e.g. ``{"backend": ["src/auth/handlers.py"], "frontend": [...]}``).
    Flatten and slice — Claude only needs a couple to disambiguate
    similar titles.
    """
    if not code_locations:
        return []
    flat: list[str] = []
    for paths in code_locations.values():
        if isinstance(paths, list):
            flat.extend(str(p) for p in paths if p)
    return flat[:limit]


async def collect_feature_dicts(
    db: AsyncSession,
    org_id: uuid.UUID,
    scan_uuid: uuid.UUID,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(existing_canonicals, new_features)`` for the merge prompt.

    The split is data-driven: any active ``feature_registry``
    knowledge_item that has a non-superseded ``synthesized_features``
    row with ``scan_id == scan_uuid`` is NEW for this scan; everything
    else is EXISTING. This makes a resumed scan after partial merge
    failure idempotent — already-merged features show up as EXISTING
    via the same join.

    Both lists are id-keyed so the caller can pass ``knowledge_items.id``
    straight into ``apply_feature_merge_plan`` ops.
    """
    ki_repo = KnowledgeItemRepository(db, org_id=org_id)
    synth_repo = SynthesizedFeatureRepository(db, org_id=org_id)

    # 1. Fetch every active feature_registry KI joined to its repos.
    ki_rows = await ki_repo.list_active_features_with_repo_names()

    grouped: dict[uuid.UUID, dict[str, Any]] = {}
    for kid, title, tags, content, repo_name in ki_rows:
        bucket = grouped.setdefault(
            kid,
            {
                "knowledge_id": str(kid),
                "title": title,
                "tags": list(tags or []),
                "content": content,
                "repo_names": [],
            },
        )
        if repo_name and repo_name not in bucket["repo_names"]:
            bucket["repo_names"].append(repo_name)

    # Drop orphans (no repo links) — they confuse Claude and the post-
    # merge audit cleanup picks them up separately.
    grouped = {kid: row for kid, row in grouped.items() if row["repo_names"]}

    # 2. Pull this scan's synthesized rows so we can split NEW vs EXISTING.
    synth_rows = await synth_repo.list_for_merge_scan(scan_uuid)

    # Latest synth row per KI wins for description/capabilities; cluster_names
    # accumulate across rows so multi-repo features keep every cluster they
    # belong to.
    new_synth: dict[uuid.UUID, dict[str, Any]] = {}
    cluster_acc: dict[uuid.UUID, list[str]] = defaultdict(list)
    for kid, description, capabilities, clusters, code_locations in synth_rows:
        new_synth[kid] = {
            "description": description,
            "capabilities": list((capabilities or {}).get("capabilities") or []),
            "code_locations": _top_code_locations(code_locations),
        }
        for cname in clusters or []:
            if cname not in cluster_acc[kid]:
                cluster_acc[kid].append(cname)

    # 3. Pull cluster_names for EXISTING rows from their latest current synth
    # row (any scan, not just this one) so the prompt has structural context.
    existing_ids = [kid for kid in grouped if kid not in new_synth]
    existing_clusters: dict[uuid.UUID, list[str]] = defaultdict(list)
    existing_synth_rows = await synth_repo.list_clusters_for_kis(existing_ids)
    for kid, clusters in existing_synth_rows:
        for cname in clusters or []:
            if cname not in existing_clusters[kid]:
                existing_clusters[kid].append(cname)

    # 4. Materialise the two output lists.
    new_features: list[dict[str, Any]] = []
    existing_canonicals: list[dict[str, Any]] = []
    for kid, row in grouped.items():
        if kid in new_synth:
            new_features.append(
                {
                    "knowledge_id": row["knowledge_id"],
                    "title": row["title"],
                    "repo_names": row["repo_names"],
                    "tags": row["tags"],
                    "cluster_names": cluster_acc.get(kid, []),
                    **new_synth[kid],
                }
            )
        else:
            existing_canonicals.append(
                {
                    "knowledge_id": row["knowledge_id"],
                    "title": row["title"],
                    "repo_names": row["repo_names"],
                    "cluster_names": existing_clusters.get(kid, []),
                    "summary": _summary_first_sentence(row["content"]),
                }
            )

    return existing_canonicals, new_features
