# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Merge fine-grained graphify clusters by their shared parent directory.

graphify's TypeScript / Python extractors detect symbol-level relations
(``calls``, ``imports_from``, ``method``, ``contains``) but the resulting
graph density on real codebases produces *very* fine-grained clusters —
often one community per source file. For our use case (Bodhi feature
synthesis) we want **domain-level** clusters: ``ais``, ``bank-feed``,
``payments`` rather than ``AisSandboxService`` and ``AisSdkService`` as
separate buckets.

This module post-processes graphify's partition by collapsing clusters
that share a common directory ancestor at ``_DIR_DEPTH``, then **adaptively
recurses one level deeper** for any bucket that looks layer-shaped
(many distinct child folders, each carrying real files). That handles
both ``src/services/<domain>/...`` (depth 3 wins) and
``src/controllers/api/<domain>/...`` (depth 4 wins) without us having to
hard-code per-language rules.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from pathlib import PurePosixPath

# Initial directory-depth budget. 3 covers the canonical
# ``src/services/<domain>`` / ``src/views/<domain>`` / ``lib/<domain>/internal``
# layouts common to JS/TS/Python/Go/Ruby. Files shallower than that fall
# back to their literal directory key so we don't over-collapse top-level
# scripts.
_DIR_DEPTH = 3

# Hard ceiling on recursion. Six segments after the deep-package skip is
# more than any real domain layout we've seen (Vue workspaces and Rails
# namespaces top out at 5). Stops pathological dirs from exploding.
_MAX_DIR_DEPTH = 6

# Recursion thresholds — we only split a bucket deeper when it both:
#   - holds enough files to look like a real layer (not a tiny utility dir), and
#   - spreads across enough child folders that going one deeper produces
#     multiple meaningful sub-buckets (each ≥ 2 files).
#
# Tuned against ATOACore's ``src/controllers/api/<domain>/`` (269 files,
# 25 child folders → recurse) vs ``src/services/payments/`` (well under
# 30 files, ≤ 2 child folders → don't recurse). Small enough that
# Rails-namespaced ``app/controllers/api/v1/<resource>_controller.rb``
# layouts still trigger; large enough that NestJS ``src/<domain>/`` and
# similar flat structures stay flat.
_RECURSE_MIN_FILES = 30
_RECURSE_MIN_SUBBUCKETS = 5


# JVM languages bury feature code under a deep package root: Maven and
# Gradle enforce ``src/main/<lang>/com/<org>/<feature>``. Without a
# sentinel-skip, every Java/Kotlin file would land in the same bucket
# at depth 3 (``src/main/java``). We skip past the standard roots so
# the depth budget reaches the actual domain segment.
_DEEP_PACKAGE_ROOTS: tuple[tuple[str, ...], ...] = (
    ("src", "main", "java"),
    ("src", "main", "kotlin"),
    ("src", "main", "scala"),
    ("src", "main", "groovy"),
    ("src", "test", "java"),
    ("src", "test", "kotlin"),
    ("src", "test", "scala"),
    # Android Studio default
    ("app", "src", "main", "java"),
    ("app", "src", "main", "kotlin"),
    ("app", "src", "test", "java"),
    ("app", "src", "test", "kotlin"),
    ("app", "src", "androidTest", "java"),
    ("app", "src", "androidTest", "kotlin"),
)


# Number of additional segments to skip past a deep-package root before
# starting to count ``_DIR_DEPTH``. The first 1-2 segments after the
# root are always the org / company package (``com.bodhi``,
# ``com.example``); the segment after that is the feature/module
# (``auth``, ``payments``).
_PACKAGE_ORG_SEGMENTS = 2


def merge_clusters_by_directory(
    partition: dict[int, list[str]],
    node_to_file: dict[str, str],
    *,
    dir_depth: int = _DIR_DEPTH,
    max_depth: int = _MAX_DIR_DEPTH,
    recurse_min_files: int = _RECURSE_MIN_FILES,
    recurse_min_subbuckets: int = _RECURSE_MIN_SUBBUCKETS,
) -> dict[int, list[str]]:
    """Collapse same-directory clusters from a graphify partition.

    Args:
        partition: Output of ``graphify.cluster.cluster`` —
            ``{cluster_idx: [node_id, …]}``.
        node_to_file: Repo-relative source file path keyed by node id.
            Nodes without a source_file are skipped from the merge logic
            and re-added as singletons keyed by their original cluster.
        dir_depth: Initial path-depth budget. Default 3.
        max_depth: Recursion ceiling. Default 6.
        recurse_min_files: Minimum bucket size before we consider going
            one level deeper. Lower this for repos with smaller layer
            dirs (e.g., 25-file controllers/api/) where the default
            (30) leaves layers mega-clustered.
        recurse_min_subbuckets: Minimum number of meaningful (≥ 2-file)
            child folders required to accept a deeper split. Tunes the
            "layer vs domain" discrimination — lower this for repos
            where layers fan out across only 3-4 child folders.

    Returns:
        A new ``{cluster_idx: [node_id]}`` dict. Cluster indices are
        re-numbered from 0; the largest bucket comes first so downstream
        code that scans a top-N gets the dominant clusters.
    """
    pairs: list[tuple[str, str]] = []
    no_file_buckets: dict[int, list[str]] = {}

    for cid, members in partition.items():
        for nid in members:
            src = node_to_file.get(nid, "")
            if src:
                pairs.append((nid, src))
            else:
                no_file_buckets.setdefault(cid, []).append(nid)

    buckets = _bucketize(
        pairs,
        depth=dir_depth,
        max_depth=max_depth,
        min_files=recurse_min_files,
        min_subbuckets=recurse_min_subbuckets,
    )

    merged: dict[int, list[str]] = {}
    next_idx = 0
    for nodes in sorted(buckets, key=len, reverse=True):
        merged[next_idx] = sorted(set(nodes))
        next_idx += 1
    for nodes in no_file_buckets.values():
        merged[next_idx] = sorted(set(nodes))
        next_idx += 1
    return merged


def _bucketize(
    pairs: list[tuple[str, str]],
    *,
    depth: int,
    max_depth: int,
    min_files: int,
    min_subbuckets: int,
) -> list[list[str]]:
    """Group ``(node_id, source_file)`` pairs by directory key, recursing
    into layer-shaped buckets one level deeper until they look domain-shaped
    or the depth ceiling kicks in.
    """
    by_key: dict[str, list[tuple[str, str]]] = {}
    for nid, src in pairs:
        by_key.setdefault(_dir_key(src, depth), []).append((nid, src))

    out: list[list[str]] = []
    for items in by_key.values():
        if depth < max_depth and _should_recurse(items, depth, min_files, min_subbuckets):
            out.extend(
                _bucketize(
                    items,
                    depth=depth + 1,
                    max_depth=max_depth,
                    min_files=min_files,
                    min_subbuckets=min_subbuckets,
                )
            )
        else:
            out.append([nid for nid, _src in items])
    return out


def _should_recurse(
    items: list[tuple[str, str]],
    depth: int,
    min_files: int,
    min_subbuckets: int,
) -> bool:
    """Decide whether bucketing this group at ``depth+1`` would produce
    a useful split.

    A bucket is a *layer* (controllers/api, routes/v1) when it both holds
    many files and fans out across many distinct child folders. A bucket
    is a *domain* (services/payments) when its files cluster in one or
    two child folders even if the file count is high. Only the layer
    case warrants deeper splitting.
    """
    if len(items) < min_files:
        return False
    deeper_keys = Counter(_dir_key(src, depth + 1) for _nid, src in items)
    # Single key at depth+1 means the deeper budget didn't add a new
    # segment (e.g. shallow paths or JVM paths already at the leaf) —
    # nothing to split.
    if len(deeper_keys) <= 1:
        return False
    meaningful = sum(1 for n in deeper_keys.values() if n >= 2)
    return meaningful >= min_subbuckets


def _dir_key(source_file: str, depth: int) -> str:
    """Return the directory key used to bucket files into clusters.

    Default behaviour: take the first ``depth`` directory components
    (good for the ``src/services/<domain>`` / ``src/views/<domain>`` /
    ``lib/<domain>/internal`` layouts common to JS/TS/Python/Go/Ruby).

    JVM exception: when the path starts with a Maven/Gradle deep root
    (``src/main/java/...`` and friends), skip past the org-package
    segment (``com.<org>``) so the budget reaches the actual feature
    namespace (``com/bodhi/auth/AuthService.java`` → bucket ``auth``).

    Root file fallback: a file with no directory at all (``README.md``
    at the repo root) gets a unique per-filename bucket so loose root
    files don't collapse into one giant cluster.
    """
    parts = PurePosixPath(source_file).parts
    dirs = parts[:-1]  # strip filename
    if not dirs:
        return f"<root>/{parts[-1] if parts else source_file}"

    for root in _DEEP_PACKAGE_ROOTS:
        if dirs[: len(root)] == root:
            shifted = dirs[len(root) + _PACKAGE_ORG_SEGMENTS :]
            if shifted:
                return "/".join(root + shifted[:depth])
            break

    return "/".join(dirs[:depth]) if len(dirs) >= depth else "/".join(dirs)


def collect_node_to_file(graph_nodes: Iterable[tuple[str, dict[str, object]]]) -> dict[str, str]:
    """Convenience: build the ``node_id → source_file`` mapping from a graph.

    Accepts the iterable returned by ``nx.Graph.nodes(data=True)``.
    """
    out: dict[str, str] = {}
    for nid, data in graph_nodes:
        src = data.get("source_file")
        if isinstance(src, str):
            out[nid] = src
    return out
