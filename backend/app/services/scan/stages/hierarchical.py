# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Stage 3 — Hierarchical re-cluster.

Builds a meta-graph from cross-cluster CALLS edges in the cached
NetworkX graph (``repo_graph_cache``), runs community detection on it,
then collapses each input community into its parent meta-community.
Output is a smaller, structurally-grouped set that's easier for
synthesis to reason about.

Why Louvain (not Leiden)?  Networkx ships ``louvain_communities``
out-of-the-box. Real Leiden via ``python-igraph + leidenalg`` requires a
C compile and a new dep. At the meta-graph scale we operate on (a few
hundred nodes, low thousands of edges) the difference is negligible —
Leiden's main win is the well-connectedness guarantee on huge sparse
graphs. We can swap the backend later via the ``algorithm`` config knob
without changing this stage's contract.

Source data: the ``repo_graph_cache`` table holds the gzipped NetworkX
graph from Stage 0 (ingest). Stage 1 (extract) gives us
``communities`` whose ``files`` lists tell us which graph nodes belong
to each cluster. We aggregate node-to-node edges in the graph into
cluster-to-cluster edges by looking up each endpoint's cluster.
"""

from __future__ import annotations

import hashlib
import uuid
from collections import Counter
from collections.abc import Iterable
from typing import Any

import networkx as nx
import structlog
from networkx.algorithms.community import louvain_communities

from app.repositories.repo_graph_cache import RepoGraphCacheRepository
from app.scan.session import with_session
from app.schemas.scan import Community
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._skip import maybe_skipped_for_ingest
from app.services.scan.stages._v2_context import resolve_v2_context

logger = structlog.get_logger(__name__)


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Group input communities into meta-communities via call-graph clustering.

    Config:
        - ``resolution`` (float, default 1.0): Louvain resolution — higher
          values produce more, smaller communities.
        - ``files_per_meta`` (int, default 30): cap on files-per-meta-
          community in the output (sampled across members by symbol count).
        - ``ingest_worktree_path`` (str): cypher cwd, threaded from Stage 0.
        - ``edges_timeout`` (int, default 120): cypher timeout for the
          edge-aggregation query.
    """
    if (
        skipped := maybe_skipped_for_ingest(config, io_label="communities → meta-communities")
    ) is not None:
        return skipped
    if not communities:
        return StageOutput(communities=[], dropped=[], extras={"reason": "no input"})

    resolution = float(config.get("resolution", 1.0))
    files_per_meta = int(config.get("files_per_meta", 30))

    v2 = resolve_v2_context(config)
    repo_id_raw = config.get("v2_repo_id")
    head_sha = str(config.get("ingest_head_sha") or "").strip()

    if v2 is None or repo_id_raw is None or not head_sha:
        # Without v2 context the graph cache cannot be loaded — return
        # the input untouched so reduction still proceeds.
        logger.info(
            "scan_hierarchical_no_v2_context",
            repo=ctx.repo_name,
        )
        return StageOutput(
            communities=communities,
            dropped=[],
            extras={"reason": "no v2 context", "io_label": "communities → meta-communities"},
        )

    repo_id = uuid.UUID(str(repo_id_raw))
    edges = await _fetch_call_edges_from_cache(
        org_id=v2.org_id,
        repo_id=repo_id,
        head_sha=head_sha,
        communities=communities,
    )
    logger.info(
        "scan_hierarchical_edges",
        repo=ctx.repo_name,
        community_count=len(communities),
        edge_count=len(edges),
    )

    by_label = {c.label: c for c in communities}
    assignments = _cluster_communities(by_label.keys(), edges, resolution=resolution)

    meta_communities = _collapse_to_meta(
        communities=communities,
        assignments=assignments,
        files_per_meta=files_per_meta,
    )

    extras: dict[str, Any] = {
        "input_count": len(communities),
        "meta_count": len(meta_communities),
        "edge_count": len(edges),
        "resolution": resolution,
        "algorithm": "louvain (networkx)",
        "io_label": "communities → meta-communities",
    }
    logger.info(
        "scan_hierarchical_done",
        repo=ctx.repo_name,
        input_count=len(communities),
        meta_count=len(meta_communities),
    )
    return StageOutput(communities=meta_communities, dropped=[], extras=extras)


async def _fetch_call_edges_from_cache(
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    head_sha: str,
    communities: list[Community],
) -> list[tuple[str, str, int]]:
    """Aggregate ``(src_label, dst_label, weight)`` cross-cluster edges.

    Loads the NetworkX call graph from ``repo_graph_cache`` and walks
    its edges. For each edge ``(u, v)`` we look up which cluster each
    endpoint belongs to via the file→cluster mapping built from
    ``communities`` and count cross-cluster pairs.

    Self-edges (an endpoint pair both in the same cluster) are dropped
    so the meta-graph is built from genuinely-cross-cluster traffic.
    Returns ``[]`` on cache miss / empty graph — the meta-graph then
    degenerates into singletons, which is correct fallback behaviour.
    """
    async with with_session(org_id) as db:
        repo = RepoGraphCacheRepository(db, org_id=org_id)
        graph = await repo.get_for_sha(repo_id=repo_id, head_sha=head_sha)
    if graph is None or graph.number_of_edges() == 0:
        logger.warning(
            "scan_hierarchical_graph_cache_miss",
            repo_id=str(repo_id),
            head_sha=head_sha[:8],
        )
        return []

    file_to_label = _build_file_to_label_map(communities)
    edge_weights: Counter[tuple[str, str]] = Counter()
    for u, v in graph.edges():
        u_label = _node_to_cluster_label(graph, u, file_to_label)
        v_label = _node_to_cluster_label(graph, v, file_to_label)
        if not u_label or not v_label or u_label == v_label:
            continue
        edge_weights[(u_label, v_label)] += 1

    return [(src, dst, w) for (src, dst), w in edge_weights.items()]


def _build_file_to_label_map(
    communities: list[Community],
) -> dict[str, str]:
    """Return ``{source_file: cluster_label}`` from the input community list."""
    mapping: dict[str, str] = {}
    for c in communities:
        for f in c.files or []:
            # When two clusters share a file (rare but possible after
            # hierarchical merges), first-write-wins so labels stay
            # deterministic. The cluster set is sorted by symbol_count
            # in the upstream stage, so we keep the largest cluster's
            # label.
            mapping.setdefault(f, c.label)
    return mapping


def _node_to_cluster_label(
    graph: nx.Graph,
    node_id: str,
    file_to_label: dict[str, str],
) -> str | None:
    """Look up a graph node's cluster label via its ``source_file`` attribute."""
    data = graph.nodes.get(node_id)
    if not data:
        return None
    src = data.get("source_file")
    if not isinstance(src, str) or not src:
        return None
    return file_to_label.get(src)


def _cluster_communities(
    nodes: Iterable[str],
    edges: list[tuple[str, str, int]],
    *,
    resolution: float,
) -> dict[str, int]:
    """Run Louvain on the meta-graph and return ``{label: meta_id}``.

    Communities with no inter-community edges become their own
    singleton meta-community — networkx puts them in their own cluster
    automatically when added as isolated nodes.
    """
    g: nx.Graph = nx.Graph()
    for label in nodes:
        g.add_node(label)
    for src, dst, weight in edges:
        if g.has_edge(src, dst):
            g[src][dst]["weight"] += weight
        else:
            g.add_edge(src, dst, weight=weight)

    clusters = louvain_communities(g, weight="weight", resolution=resolution, seed=42)
    assignments: dict[str, int] = {}
    for idx, members in enumerate(clusters):
        for label in members:
            assignments[label] = idx
    return assignments


def _collapse_to_meta(
    *,
    communities: list[Community],
    assignments: dict[str, int],
    files_per_meta: int,
    top_label_count: int = 3,
) -> list[Community]:
    """Fold input communities into meta-communities, summing stats.

    Meta-community label is built from the top-``top_label_count``
    distinct constituent labels by symbol count, joined with ``" + "``
    (e.g. ``"Payments + Invoice + Refunds"``).

    **Identity-preservation rule.** Louvain frequently bundles dozens of
    clusters into a single meta when the call graph is dense. Any
    constituent cluster whose label would NOT make it into the composite
    (i.e. whose label is hidden behind the top-N) loses its identity
    entirely — synthesis never sees its name in the meta label, and its
    files often don't survive the ``files_per_meta`` cap either. To keep
    the synthesis prompt honest, any cluster whose label is hidden gets
    promoted to its own singleton meta. The remaining (visible) clusters
    stay merged. This is fully generic: it uses the existing
    ``top_label_count`` threshold and the cluster's own derived label,
    with no hardcoded domain vocabulary.

    Files are unioned across the kept members preserving rank order,
    capped at ``files_per_meta``.
    """
    grouped: dict[int, list[Community]] = {}
    for comm in communities:
        meta_id = assignments.get(comm.label)
        if meta_id is None:
            # Isolated node — give it its own bucket keyed by a stable
            # hash of the label. ``hash()`` is randomised across Python
            # processes (PYTHONHASHSEED), so we use a sha256 prefix to
            # keep meta_ids reproducible across container restarts.
            digest = hashlib.sha256(comm.label.encode("utf-8")).digest()
            meta_id = -int.from_bytes(digest[:4], "big")
        grouped.setdefault(meta_id, []).append(comm)

    metas: list[Community] = []
    for meta_id, members in grouped.items():
        members_sorted = sorted(members, key=lambda c: c.symbol_count, reverse=True)

        # Compute which distinct labels survive in the composite. Any
        # member whose label is NOT in this set has its identity
        # hidden — promote it to its own singleton meta.
        visible_labels: list[str] = []
        for m in members_sorted:
            if m.label in visible_labels:
                continue
            visible_labels.append(m.label)
            if len(visible_labels) >= top_label_count:
                break
        visible_set = set(visible_labels)

        kept = [m for m in members_sorted if m.label in visible_set]
        hidden = [m for m in members_sorted if m.label not in visible_set]

        if kept:
            metas.append(
                _build_meta_community(
                    members=kept,
                    files_per_meta=files_per_meta,
                    top_label_count=top_label_count,
                    meta_id_seed=str(meta_id),
                )
            )
        # Group hidden clusters by their (shared) label so multiple
        # constituents with the same name collapse into one promoted
        # meta rather than creating duplicate features. Clusters end
        # up here when they shared a meta_id under Louvain (i.e. they
        # really do call each other heavily) — keeping them grouped
        # respects that signal.
        hidden_by_label: dict[str, list[Community]] = {}
        for h in hidden:
            hidden_by_label.setdefault(h.label, []).append(h)
        for label, h_members in hidden_by_label.items():
            metas.append(
                _build_meta_community(
                    members=h_members,
                    files_per_meta=files_per_meta,
                    top_label_count=top_label_count,
                    meta_id_seed=f"{meta_id}:{label}",
                )
            )

    metas.sort(key=lambda c: c.symbol_count, reverse=True)
    return metas


def _build_meta_community(
    *,
    members: list[Community],
    files_per_meta: int,
    top_label_count: int,
    meta_id_seed: str,
) -> Community:
    """Build one ``Community`` from a list of constituent clusters."""
    members_sorted = sorted(members, key=lambda c: c.symbol_count, reverse=True)
    anchor = members_sorted[0]
    total_symbols = sum(m.symbol_count for m in members_sorted)
    composite_label = _composite_label(members_sorted, top_n=top_label_count)
    source_ids = _collect_source_ids(members_sorted)

    sampled_files: list[str] = []
    seen: set[str] = set()
    for member in members_sorted:
        for f in member.files:
            if f in seen:
                continue
            seen.add(f)
            sampled_files.append(f)
            if len(sampled_files) >= files_per_meta:
                break
        if len(sampled_files) >= files_per_meta:
            break

    return Community(
        label=composite_label,
        heuristic_label=anchor.heuristic_label,
        symbol_count=total_symbols,
        cohesion=anchor.cohesion,
        files=sampled_files,
        meta_community_id=meta_id_seed,
        source_community_ids=source_ids,
    )


def _composite_label(members: list[Community], *, top_n: int) -> str:
    """Build a meta-community label from its top-N constituent labels.

    Single-member metas keep their original label so the UI shows
    ``"Payments"`` instead of redundant ``"Payments"``-only composite
    plumbing. Duplicate labels are deduplicated while preserving order
    (a meta can absorb several already-merged ``Payments`` rows in
    edge cases — show the label once).
    """
    if len(members) == 1:
        return members[0].label

    seen: set[str] = set()
    chosen: list[str] = []
    for m in members:
        if m.label in seen:
            continue
        seen.add(m.label)
        chosen.append(m.label)
        if len(chosen) >= top_n:
            break
    return " + ".join(chosen)


def _collect_source_ids(members: list[Community]) -> list[str]:
    """Aggregate every constituent's source/community id for traceability."""
    ids: list[str] = []
    seen: set[str] = set()
    for m in members:
        for cid in [*m.source_community_ids, m.community_id]:
            if cid and cid not in seen:
                seen.add(cid)
                ids.append(cid)
    return ids
