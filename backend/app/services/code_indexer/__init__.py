# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Code-graph indexer for bodhiorchard scans.

Replaces the legacy ``gitnexus_indexer`` module. Drives community
detection through the MIT-licensed ``graphifyy`` library (tree-sitter
extraction → NetworkX graph → Leiden / Louvain clustering with
oversize-split rule) instead of the npx GitNexus CLI.

Public API:

- :class:`ClusterEntry` — one community + its files + symbols + label.
- :class:`IndexResult` — a complete index of a repo at a given SHA.
- :func:`index_repo` — async entrypoint used by the scan pipeline.

Determinism is provided by:

1. graphify's internal seed pinning (Leiden seeded by graspologic; the
   Louvain fallback uses ``seed=42``).
2. :mod:`app.services.code_indexer.seed` re-orders the partition by
   ``(size desc, min_member_id asc, head_sha_xor)`` so identical SHAs
   always produce identical cluster_ids.
3. :mod:`app.services.code_indexer.labeling` produces deterministic
   path-token TF-IDF labels.

The ``IndexResult.clusters`` list is ordered largest-first.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import structlog
from graphify.build import build as gx_build
from graphify.cluster import cluster as gx_cluster
from graphify.cluster import cohesion_score
from graphify.extract import collect_files as gx_collect_files
from graphify.extract import extract as gx_extract

from app.services.code_indexer.labeling import build_corpus_tokens, label_cluster
from app.services.code_indexer.merge_by_dir import merge_clusters_by_directory
from app.services.code_indexer.seed import cluster_signature, order_partition
from app.services.code_indexer.skip_lists import filter_paths

logger = structlog.get_logger(__name__)


# graphify's ``collect_files`` hardcodes a 25-suffix allow-list that omits
# ten extensions its own ``_DISPATCH`` table already routes to a working
# extractor. The result: Vue / Svelte / Flutter / React-JSX / Elixir /
# Julia / Verilog repos collect zero source files even though graphify can
# parse them. We close the gap by re-walking the tree for the missing
# suffixes and unioning with graphify's own output. ``filter_paths`` runs
# right after, so vendored hits inside ``node_modules`` / ``.nuxt`` /
# ``.dart_tool`` are dropped without extra work here.
_EXTRA_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".vue",  # Vue SFC (Nuxt, Vite)
        ".svelte",  # Svelte / SvelteKit
        ".jsx",  # React (JS variant) — .tsx already collected
        ".mjs",  # ES modules
        ".dart",  # Flutter / Dart
        ".ex",  # Elixir source
        ".exs",  # Elixir scripts
        ".jl",  # Julia
        ".v",  # Verilog
        ".sv",  # SystemVerilog
    }
)


def _collect_repo_files(repo: Path) -> list[Path]:
    """Wrap ``gx_collect_files`` to include extensions graphify forgot.

    Graphify can extract every suffix in ``_EXTRA_EXTENSIONS`` (its
    ``_DISPATCH`` maps them to a real extractor) but its file walker
    doesn't list them. We rglob each missing suffix and union with
    graphify's output, skipping dotfile / dotdir paths the same way
    graphify does internally. Vendor filtering happens in the caller's
    ``filter_paths`` step, so we don't duplicate it here.
    """
    base = list(gx_collect_files(repo))
    seen: set[Path] = set(base)
    for ext in _EXTRA_EXTENSIONS:
        for p in repo.rglob(f"*{ext}"):
            if any(part.startswith(".") for part in p.parts):
                continue
            if p in seen:
                continue
            seen.add(p)
            base.append(p)
    return sorted(base)


@dataclass(frozen=True, slots=True)
class ClusterEntry:
    """One community produced by the indexer.

    ``signature`` is the SHA-256 of the canonical (sorted) member node
    ID list — stable across SHAs when the cluster's contents are
    unchanged. Used downstream as the reconciler's primary identity key.
    """

    cluster_id: str
    label: str
    files: list[str]
    symbols: list[str]
    symbol_count: int
    signature: str
    cohesion: float | None = None


@dataclass
class IndexResult:
    """Complete index of a repo at a head_sha."""

    head_sha: str
    clusters: list[ClusterEntry] = field(default_factory=list)
    graph: nx.Graph | None = None
    elapsed_s: float = 0.0
    file_count: int = 0
    success: bool = False
    error: str | None = None


async def index_repo(
    repo_path: str | Path,
    *,
    head_sha: str = "",
    max_files: int = 50_000,
) -> IndexResult:
    """Index a repository: parse → build call graph → cluster.

    Args:
        repo_path: Absolute path to the git working tree.
        head_sha: Optional git SHA. Used to seed cluster ordering and
            label tie-breakers so re-runs on the same SHA produce
            identical output. Pass an empty string for sandbox usage.
        max_files: Skip directories whose discovery exceeds this cap.
            Prevents accidental indexing of monorepos with vendored
            content (``node_modules``, ``vendor/``).

    Returns:
        IndexResult — ``success=False`` and ``error`` populated on
        controlled failure (parse error, oversized repo, etc.). Raises
        only on programmer error.
    """
    t0 = time.monotonic()
    repo = Path(repo_path).resolve()
    result = IndexResult(head_sha=head_sha or "")

    if not repo.exists():
        result.error = f"repo path not found: {repo!s}"
        return result

    try:
        raw_files = await asyncio.to_thread(_collect_repo_files, repo)
    except Exception as exc:  # noqa: BLE001 — narrow on next iter
        result.error = f"collect_files failed: {exc}"
        result.elapsed_s = round(time.monotonic() - t0, 2)
        return result

    # Drop vendored / build / cache content. graphify's own skip set
    # only catches a handful of asset bundles; we add cross-language
    # rules (node_modules, target, vendor, Pods, _build, …). Without
    # this, a Node.js project's node_modules drowns the actual src
    # tree by 20:1 and Leiden produces giant library-symbol clusters.
    files, dropped = filter_paths(raw_files, repo)
    if dropped:
        logger.info(
            "code_indexer_skip_filter",
            repo=str(repo),
            kept=len(files),
            dropped=dropped,
            ratio=f"{dropped / (dropped + len(files)):.0%}",
        )

    result.file_count = len(files)
    if not files:
        result.error = "no source files found"
        result.success = True  # not a failure — just empty
        result.elapsed_s = round(time.monotonic() - t0, 2)
        return result

    if len(files) > max_files:
        logger.warning(
            "code_indexer_file_cap_hit",
            repo=str(repo),
            file_count=len(files),
            cap=max_files,
        )
        result.error = f"file count {len(files)} exceeds cap {max_files}"
        result.elapsed_s = round(time.monotonic() - t0, 2)
        return result

    try:
        extraction = await asyncio.to_thread(gx_extract, files, repo)
    except Exception as exc:  # noqa: BLE001
        result.error = f"extract failed: {exc}"
        result.elapsed_s = round(time.monotonic() - t0, 2)
        return result

    try:
        # Build directed so ``code_impact`` can distinguish callers from
        # callees. graphify's ``cluster.cluster`` internally converts to
        # undirected before running Leiden, so the partition is unaffected.
        graph: nx.Graph = await asyncio.to_thread(gx_build, [extraction], directed=True)
    except Exception as exc:  # noqa: BLE001
        result.error = f"build_graph failed: {exc}"
        result.elapsed_s = round(time.monotonic() - t0, 2)
        return result

    result.graph = graph

    if graph.number_of_nodes() == 0:
        result.success = True
        result.elapsed_s = round(time.monotonic() - t0, 2)
        return result

    try:
        partition = await asyncio.to_thread(gx_cluster, graph)
    except Exception as exc:  # noqa: BLE001
        result.error = f"cluster failed: {exc}"
        result.elapsed_s = round(time.monotonic() - t0, 2)
        return result

    # graphify's symbol-level partition is too fine-grained for our
    # synthesis use case — TypeScript especially produces one cluster
    # per source file. Merge by parent-directory so ``src/services/ais/*``
    # ends up as one ``ais`` cluster regardless of how many files /
    # symbols sit inside.
    node_to_file = {
        nid: str(data.get("source_file", ""))
        for nid, data in graph.nodes(data=True)
        if isinstance(data.get("source_file"), str)
    }
    partition = merge_clusters_by_directory(partition, node_to_file)

    ordered = order_partition(partition, head_sha=head_sha)

    # Build the FILE-level "all corpus paths" set once, then pre-compute
    # the corpus-token Counter so every per-cluster ``label_cluster`` call
    # reuses the same tokenisation (saves O(N·C) on large repos).
    corpus_files: list[str] = list(_iter_files_from_graph(graph))
    corpus_tokens_counter = build_corpus_tokens(corpus_files) if corpus_files else None

    entries: list[ClusterEntry] = []
    for cluster_id, member_node_ids in ordered:
        files_in_cluster, symbols_in_cluster = _partition_files_and_symbols(graph, member_node_ids)
        if not files_in_cluster and not symbols_in_cluster:
            # Empty cluster (shouldn't happen) — skip rather than emit junk.
            continue
        label = label_cluster(
            files_in_cluster or [n for n in member_node_ids],
            corpus_tokens=corpus_tokens_counter,
        )
        try:
            cohesion = cohesion_score(graph, member_node_ids)
        except Exception:  # noqa: BLE001 — graphify cohesion is best-effort
            cohesion = None
        files_sorted = sorted(set(files_in_cluster))
        symbols_sorted = sorted(set(symbols_in_cluster))
        entries.append(
            ClusterEntry(
                cluster_id=cluster_id,
                label=label,
                files=files_sorted,
                symbols=symbols_sorted,
                symbol_count=len(member_node_ids),
                signature=cluster_signature(files_sorted, symbols_sorted),
                cohesion=cohesion,
            )
        )

    result.clusters = entries
    result.success = True
    result.elapsed_s = round(time.monotonic() - t0, 2)
    logger.info(
        "code_indexer_done",
        repo=str(repo),
        head_sha=(head_sha or "")[:8],
        files=result.file_count,
        nodes=graph.number_of_nodes(),
        edges=graph.number_of_edges(),
        clusters=len(entries),
        elapsed_s=result.elapsed_s,
    )
    return result


def _iter_files_from_graph(graph: nx.Graph) -> list[str]:
    """Return repo-relative source_file values from every node in the graph."""
    seen: set[str] = set()
    for _node_id, data in graph.nodes(data=True):
        src = data.get("source_file")
        if isinstance(src, str) and src:
            seen.add(src)
    return sorted(seen)


def _partition_files_and_symbols(
    graph: nx.Graph,
    member_node_ids: list[str],
) -> tuple[list[str], list[str]]:
    """Split a cluster's member node ids into source files and symbol labels.

    graphify's extractor produces both file-level nodes (``source_file``
    set, label ends in an extension) and symbol-level nodes (functions,
    classes, methods) tagged with the same ``source_file`` value.
    Cluster cards list both — files for code_locations, symbols for
    descriptions.
    """
    files: set[str] = set()
    symbols: list[str] = []
    for nid in member_node_ids:
        if nid not in graph:
            continue
        data = graph.nodes[nid]
        src = data.get("source_file")
        if isinstance(src, str) and src:
            files.add(src)
        label = data.get("label")
        if isinstance(label, str) and label and not _is_file_label(label):
            symbols.append(label)
    return sorted(files), symbols


def _is_file_label(label: str) -> bool:
    """Heuristic: graphify uses the bare filename as the label for file nodes."""
    return "." in label and "/" not in label and "(" not in label and " " not in label
