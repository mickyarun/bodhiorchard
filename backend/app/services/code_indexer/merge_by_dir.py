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
that share a common directory ancestor. We use a tunable depth knob
(``DIR_DEPTH``) so that ``src/services/ais/foo.ts`` and
``src/services/ais/bar.ts`` merge under ``ais/`` (depth=3) but
``src/services/ais/...`` and ``src/services/bankFeed/...`` stay
separate. Files outside the configured roots fall through unmerged.

The ``merge_clusters_by_directory`` function takes graphify's
``{cluster_idx: [node_ids]}`` partition and a node→source_file mapping,
returns a new partition with same shape but with domain-merged
membership.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import PurePosixPath

# How many directory components to consider when bucketing.
# 3 covers the canonical "src/services/<domain>" / "src/views/<domain>" /
# "lib/<domain>/internal" layouts. Files shallower than that fall back
# to their literal directory key so we don't over-collapse top-level
# scripts (e.g. ``src/index.ts``).
_DIR_DEPTH = 3


# JVM languages bury feature code under a deep package root: Maven and
# Gradle enforce ``src/main/<lang>/com/<org>/<feature>``. Without a
# sentinel-skip, every Java/Kotlin file would land in the same bucket
# at depth 3 (``src/main/java``). We skip past the standard roots so
# the depth budget reaches the actual domain segment. The list is a
# Maven/Gradle convention, not a project-specific assumption.
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
# (``auth``, ``payments``). Skipping the org segment puts us in
# feature-namespace territory.
_PACKAGE_ORG_SEGMENTS = 2


def merge_clusters_by_directory(
    partition: dict[int, list[str]],
    node_to_file: dict[str, str],
    *,
    dir_depth: int = _DIR_DEPTH,
) -> dict[int, list[str]]:
    """Collapse same-directory clusters from a graphify partition.

    Args:
        partition: Output of ``graphify.cluster.cluster`` —
            ``{cluster_idx: [node_id, …]}``.
        node_to_file: Repo-relative source file path keyed by node id.
            Nodes without a source_file are skipped from the merge logic
            and re-added as singletons keyed by their original cluster.
        dir_depth: Number of leading path components to use as the merge
            key. Default 3 (``src/services/ais``-shaped layouts).

    Returns:
        A new ``{cluster_idx: [node_id]}`` dict where node ids that
        belong to the same directory bucket end up in the same cluster.
    """
    bucket_of: dict[str, list[str]] = {}
    no_file_buckets: dict[int, list[str]] = {}

    for cid, members in partition.items():
        for nid in members:
            src = node_to_file.get(nid, "")
            if not src:
                no_file_buckets.setdefault(cid, []).append(nid)
                continue
            key = _dir_key(src, dir_depth)
            bucket_of.setdefault(key, []).append(nid)

    # Re-emit as {idx: [members]} starting from 0 so cluster ids stay
    # tightly packed.
    merged: dict[int, list[str]] = {}
    next_idx = 0
    for nodes in sorted(bucket_of.values(), key=len, reverse=True):
        merged[next_idx] = sorted(set(nodes))
        next_idx += 1
    for nodes in no_file_buckets.values():
        merged[next_idx] = sorted(set(nodes))
        next_idx += 1
    return merged


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

    # Detect a JVM-style deep root and shift the depth window past the
    # org package segments.
    for root in _DEEP_PACKAGE_ROOTS:
        if dirs[: len(root)] == root:
            shifted = dirs[len(root) + _PACKAGE_ORG_SEGMENTS :]
            if shifted:
                # Use the deep root as a stable prefix so two clusters
                # under different Maven roots can't accidentally merge.
                return "/".join(root + shifted[:depth])
            # Fall through if the path is shallower than the org skip.
            break

    return "/".join(dirs[:depth]) if len(dirs) >= depth else "/".join(dirs)


def collect_node_to_file(graph_nodes: Iterable[tuple[str, dict]]) -> dict[str, str]:
    """Convenience: build the ``node_id → source_file`` mapping from a graph.

    Accepts the iterable returned by ``nx.Graph.nodes(data=True)``.
    """
    return {
        nid: data.get("source_file", "")
        for nid, data in graph_nodes
        if isinstance(data.get("source_file"), str)
    }
