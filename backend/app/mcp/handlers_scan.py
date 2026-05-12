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

"""MCP handlers exclusive to the scan pipeline.

The single tool is ``write_synthesis_feature`` — Claude calls it once
per feature it produces during the synthesize stage. The handler
appends a ``FeatureWrite`` to the per-repo accumulator; the
synthesise stage drains the accumulator at end-of-batch and feeds it
to :mod:`app.services.feature_reconciler` which performs all DB
writes.

The handler also derives a stable ``cluster_signature`` for the
emitted feature by combining the underlying clusters' signatures
from ``cluster_cache``. That gives the reconciler a structural
identity key independent of LLM-generated titles or per-scan
``cluster_id`` numbering.
"""

from __future__ import annotations

import hashlib
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
from app.services.code_indexer.labeling import extract_path_tokens, extract_text_tokens

logger = structlog.get_logger(__name__)


async def handle_write_synthesis_feature(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Stage one synthesised feature for end-of-batch reconciliation.

    Required params: ``name``, ``description``, ``source_community_ids``
    (non-empty list of community_id strings — the ids you saw in the
    prompt's JSON payload), ``repo_name``.

    Optional: ``dropped_community_ids``, ``capabilities``,
    ``code_locations``, ``tags``, ``repo_id``. ``repo_id`` comes from
    the synthesis prompt's *Scan context* block; when supplied it
    survives renames mid-scan and saves a name-resolution round-trip.

    The handler derives a stable ``cluster_signature`` for the
    feature by combining the per-cluster signatures from
    ``cluster_cache``. The reconciler uses that as its primary
    identity key on the next reconcile pass.
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
    code_locations, cluster_signature = await _expand_and_signature(
        db,
        org_id=org.id,
        repo_id=repo_id,
        source_ids=source_ids,
        existing=code_locations,
        feature_text=f"{feature_name} {description}",
    )

    queued = await persist_synth_feature(
        db=db,
        org=org,
        repo_id=repo_id,
        feature_title=title,
        description=description,
        capabilities=capabilities,
        cluster_names=source_ids,
        cluster_signature=cluster_signature,
        code_locations=code_locations,
        tags=tags,
    )

    logger.info(
        "scan_write_synthesis_feature",
        org_id=str(org.id),
        repo=repo_name,
        title=title,
        source_count=len(source_ids),
        dropped_count=len(dropped_ids),
        cluster_signature=cluster_signature[:12],
        queued_in_batch=queued,
    )
    return {
        "success": True,
        "title": title,
        "source_count": len(source_ids),
        "dropped_count": len(dropped_ids),
        "queued_in_batch": queued,
    }


# --- helpers --------------------------------------------------------


_CLUSTER_ID_RE = re.compile(r"^c\d+$")
"""Cluster id format emitted by ``code_indexer.seed.stable_cluster_id``."""

# Path heuristics for layer assignment when expanded files land outside
# Claude's existing layer buckets. Same regexes as ``coverage_audit``.
_FRONTEND_EXT_RE = re.compile(r"\.(vue|svelte|astro|tsx|jsx)$")
_FRONTEND_DIRS_RE = re.compile(r"/(views|pages|components|composables|stores|layouts)/")
_BATCH_DIRS_RE = re.compile(r"/(cron|jobs?|workers|batch|queue|tasks?|schedule)/")


async def _expand_and_signature(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    source_ids: list[str],
    existing: Any,
    feature_text: str = "",
) -> tuple[dict[str, list[str]], str]:
    """Expand ``code_locations`` AND derive a stable ``cluster_signature``.

    Looks up every ``c<N>`` cluster id in ``source_community_ids``
    against ``cluster_cache`` for the repo's current head SHA, unions
    their files into ``existing`` keyed by layer (auto-classifying
    paths the LLM didn't bucket itself), and combines their
    individual signatures into one structural identity for the
    feature: ``sha256(sorted([sig1, sig2, ...]))``.

    Domain-overlap guard: when ``feature_text`` is provided, a cluster
    is dropped from the union when its full token vocabulary shares
    *zero* tokens with the title+description vocabulary. That's the
    server-side defense against the LLM lumping unrelated clusters
    under one feature (e.g. clusters from an unrelated domain getting
    attached because both happen to carry ambiguous one-word labels in
    the synthesis prompt). The guard only fires on no-overlap — partial
    overlap is treated as valid since legitimate features can span
    clusters with different domain nouns.

    When no source_ids resolve (older prompts that emit composite
    labels, or a cache miss), falls back to a label-derived
    signature so the writer never produces an empty-string signature
    that would collide across unrelated features.
    """
    candidate_ids = [s for s in source_ids if isinstance(s, str) and _CLUSTER_ID_RE.match(s)]

    head_sha = await _latest_head_sha(db, org_id=org_id, repo_id=repo_id)
    feature_tokens = extract_text_tokens(feature_text) if feature_text else set()

    base: dict[str, list[str]] = {}
    if isinstance(existing, dict):
        for layer, files in existing.items():
            if not isinstance(layer, str) or not isinstance(files, list):
                continue
            kept: list[str] = []
            for f in files:
                if not isinstance(f, str):
                    continue
                # LLM-supplied paths are *logged* on no-overlap, never dropped.
                # The model's direct ``code_locations`` output is intent; the
                # cluster-expansion path below is our inference and is the only
                # place we suppress data. Telemetry stays here so we can audit
                # how often the model wedges out-of-domain paths into a
                # feature.
                if not _path_overlaps_feature(f, feature_tokens):
                    logger.warning(
                        "synth_feature_file_no_domain_overlap",
                        layer=layer,
                        file_path=f,
                        decision="kept",
                    )
                kept.append(f)
            base[layer] = kept

    constituent_signatures: list[str] = []
    if candidate_ids and head_sha:
        cc_repo = ClusterCacheRepository(db, org_id=org_id)
        cached_rows = await cc_repo.list_for_repo_sha(repo_id=repo_id, head_sha=head_sha)
        by_id = {row.cluster_id: row for row in cached_rows}

        seen: set[str] = {f for layer_files in base.values() for f in layer_files}
        layered: dict[str, list[str]] = defaultdict(list, {k: list(v) for k, v in base.items()})

        for cid in candidate_ids:
            cluster = by_id.get(cid)
            if cluster is None:
                continue
            if not _cluster_overlaps_feature(cluster.files, feature_tokens):
                logger.warning(
                    "synth_feature_cluster_rejected",
                    reason="no_domain_overlap",
                    cluster_id=cid,
                    cluster_label=cluster.label,
                    sample_file=(cluster.files or [None])[0],
                )
                continue
            if cluster.signature:
                constituent_signatures.append(cluster.signature)
            for f in cluster.files or []:
                if not isinstance(f, str) or f in seen:
                    continue
                seen.add(f)
                layered[_classify_layer(f)].append(f)

        merged_locations = dict(layered)
    else:
        merged_locations = base

    signature = _combine_signatures(constituent_signatures, fallback=str(source_ids))
    return merged_locations, signature


def _cluster_overlaps_feature(cluster_files: list[str] | None, feature_tokens: set[str]) -> bool:
    """True when the cluster's token vocabulary overlaps the feature text.

    Used as a soft guard against LLM cross-contamination. Returns True
    when either side has no signal (no feature text supplied, no cluster
    files) so we don't suppress data on missing information; only the
    no-overlap-with-data case rejects.
    """
    if not feature_tokens or not cluster_files:
        return True
    cluster_tokens = extract_path_tokens(cluster_files)
    if not cluster_tokens:
        return True
    return not cluster_tokens.isdisjoint(feature_tokens)


def _path_overlaps_feature(file_path: str, feature_tokens: set[str]) -> bool:
    """True when a single file's path vocabulary overlaps the feature text.

    Per-file variant of :func:`_cluster_overlaps_feature`. Pure predicate —
    the *caller* decides whether to drop or merely log. The cluster handler
    drops on False; the LLM-supplied-paths handler emits a warning and keeps
    the file. Keeping the function action-free lets each call site own its
    own policy.
    """
    if not feature_tokens:
        return True
    path_tokens = extract_path_tokens([file_path])
    if not path_tokens:
        return True
    return not path_tokens.isdisjoint(feature_tokens)


def _combine_signatures(individual: list[str], *, fallback: str) -> str:
    """SHA-256 of the sorted list of constituent cluster signatures.

    Stable across re-scans whenever the underlying cluster set is
    unchanged. ``fallback`` is hashed when the lookup produced no
    cluster signatures (older prompts, cache miss) so we never
    return an empty string that would collide across features.
    """
    canonical = "\n".join(sorted(individual)) if individual else f"fallback:{fallback}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
