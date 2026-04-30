# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Data collection for the cross-repo feature merge prompt.

Splits the org's feature set into two groups for the two-section prompt:

- **NEW** — unmerged ``synthesized_features`` rows for this scan
  (``merge_outcome IS NULL``). Keyed by ``synth_id`` so merge ops
  reference rows that have no canonical KI yet.
- **EXISTING** — active ``feature_registry`` knowledge_items from
  prior scans. Keyed by ``knowledge_id``.

NEW rows carry ``description`` / ``capabilities`` / ``code_locations``
straight from the synth row. EXISTING rows pull a one-line ``summary``
from ``knowledge_items.content`` (the canonical merged view). Cluster
names accumulate across rows so multi-repo features keep every cluster
they belong to.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.synthesized_feature import SynthesizedFeatureRepository
from app.repositories.tracked_repository import TrackedRepoRepository


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

    NEW rows come from every unmerged ``synthesized_features`` row in
    the org — not just this scan's — so stragglers from prior cancelled
    / partial scans get folded into the dedup pass. ``scan_uuid`` is
    accepted only for log context. EXISTING rows come from active
    ``feature_registry`` knowledge_items, keyed by ``knowledge_id``.
    Resuming a scan after a partial merge failure is idempotent: rows
    that have already been promoted to KI carry a non-NULL
    ``merge_outcome`` and drop out of the NEW set automatically.
    """
    del scan_uuid  # kept in signature for caller log context only
    ki_repo = KnowledgeItemRepository(db, org_id=org_id)
    synth_repo = SynthesizedFeatureRepository(db, org_id=org_id)
    tr_repo = TrackedRepoRepository(db, org_id=org_id)

    # 1. NEW: every unmerged synth row in the org, regardless of scan.
    synth_rows = await synth_repo.list_unmerged_org_wide()
    repo_name_by_id: dict[uuid.UUID, str] = {}
    if synth_rows:
        for repo in await tr_repo.list_active():
            repo_name_by_id[repo.id] = repo.name

    # Group by feature_title so multi-repo features merge into one prompt
    # row (cluster names accumulate, repo names dedupe). Within a group
    # the latest synth row wins for description/capabilities — the synth
    # repo orders by ``synthesized_at`` ascending so the last-seen entry
    # is the freshest take.
    grouped_new: dict[str, dict[str, Any]] = {}
    for synth in synth_rows:
        bucket = grouped_new.setdefault(
            synth.feature_title,
            {
                "synth_id": str(synth.id),
                "title": synth.feature_title,
                "repo_names": [],
                "tags": [],
                "cluster_names": [],
                "description": synth.description,
                "capabilities": list((synth.capabilities or {}).get("capabilities") or []),
                "code_locations": _top_code_locations(synth.code_locations),
            },
        )
        # Latest row wins for descriptive fields.
        bucket["synth_id"] = str(synth.id)
        bucket["description"] = synth.description
        bucket["capabilities"] = list((synth.capabilities or {}).get("capabilities") or [])
        bucket["code_locations"] = _top_code_locations(synth.code_locations)

        repo_name = repo_name_by_id.get(synth.repo_id)
        if repo_name and repo_name not in bucket["repo_names"]:
            bucket["repo_names"].append(repo_name)
        for cname in synth.cluster_names or []:
            if cname not in bucket["cluster_names"]:
                bucket["cluster_names"].append(cname)
            if cname not in bucket["tags"]:
                bucket["tags"].append(cname)

    new_features: list[dict[str, Any]] = list(grouped_new.values())

    # 2. EXISTING: active feature_registry KIs from prior scans.
    ki_rows = await ki_repo.list_active_features_with_repo_names()
    grouped_existing: dict[uuid.UUID, dict[str, Any]] = {}
    for kid, title, tags, content, repo_name in ki_rows:
        bucket = grouped_existing.setdefault(
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

    # Drop orphans (no repo links) for canonicals that came from code
    # scans — they confuse Claude. Keep planned/in_progress KIs even
    # without repo links so PR-tracking-driven planned BUDs remain
    # visible to the merge prompt for future absorbs.
    grouped_existing = {kid: row for kid, row in grouped_existing.items() if row["repo_names"]}

    existing_ids = list(grouped_existing.keys())
    existing_clusters: dict[uuid.UUID, list[str]] = defaultdict(list)
    if existing_ids:
        for kid, clusters in await synth_repo.list_clusters_for_kis(existing_ids):
            for cname in clusters or []:
                if cname not in existing_clusters[kid]:
                    existing_clusters[kid].append(cname)

    existing_canonicals: list[dict[str, Any]] = []
    for kid, row in grouped_existing.items():
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
