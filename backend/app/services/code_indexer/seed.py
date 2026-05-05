# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Deterministic cluster ordering keyed off ``head_sha``.

graphify's ``cluster.cluster`` is internally deterministic: Leiden via
graspologic uses a fixed seed when called without args, and the Louvain
fallback in graphify's own code hardcodes ``seed=42``. So the partition
itself is reproducible across runs *of the same NetworkX graph*.

What graphify does NOT control is the **ordering** of communities in the
returned dict, which depends on Python dict insertion order and (for
Leiden) on graspologic's internal traversal. We sort the partition by
size-descending and hash the head_sha into the tiebreak so multiple
clusters of equal size still come back in a stable order.

Result: identical SHA → identical cluster IDs (``c0``, ``c1``, …) and
identical labels. Different SHA → potentially renumbered clusters,
which is correct because the underlying graph changed.
"""

from __future__ import annotations

import hashlib


def stable_cluster_id(idx: int) -> str:
    """Return the canonical cluster_id for partition index ``idx``."""
    return f"c{idx}"


def head_sha_seed(head_sha: str | None) -> int:
    """Derive a 32-bit deterministic seed from a git SHA.

    Returns 0 for a missing SHA so unit tests without git context still
    get a stable seed.
    """
    if not head_sha:
        return 0
    digest = hashlib.sha256(head_sha.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def cluster_signature(files: list[str], symbols: list[str]) -> str:
    """SHA-256 hex of a cluster's canonical node-ID list.

    Stable structural identity for incremental feature reconciliation:
    re-clustering the same code under a different head SHA produces the
    same signature when the member set is unchanged. graphify's
    extraction is already deterministic, so the same input graph always
    yields the same files + symbols here.

    Used by :mod:`app.services.feature_reconciler` as the primary
    identity key for matching synthesised features to existing rows.
    LLM-generated titles drift between scans; the signature does not.
    """
    canonical = "\n".join(sorted(files) + sorted(symbols))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def order_partition(
    partition: dict[int, list[str]],
    *,
    head_sha: str | None,
) -> list[tuple[str, list[str]]]:
    """Sort the partition deterministically and assign canonical IDs.

    Sort key:
        1. cluster size descending (largest first)
        2. lexicographically smallest member node id (tiebreak)
        3. head_sha-derived integer (final tiebreak so unrelated SHAs
           don't always pick the same loser of a tie)

    Returns a list of ``(cluster_id, members)`` pairs ordered for write.
    """
    seed = head_sha_seed(head_sha)
    sorted_items = sorted(
        partition.items(),
        key=lambda kv: (
            -len(kv[1]),
            min(kv[1]) if kv[1] else "",
            (kv[0] ^ seed) & 0xFFFFFFFF,
        ),
    )
    return [(stable_cluster_id(i), members) for i, (_old_id, members) in enumerate(sorted_items)]
