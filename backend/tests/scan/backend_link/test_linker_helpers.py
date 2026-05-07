# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Unit tests for the pure-Python helpers in ``backend_link.linker_helpers``.

The previous helper (``bucket_paths_per_repo``) discarded the file path
returned by :class:`BackendIndex.lookup`. The replacement
``bucket_per_repo`` keeps both halves so each :class:`BackendBucket`
carries the api_paths AND the declaring file_paths — exactly what the
BACKEND ``feature_to_repo`` row needs to populate ``code_locations``
alongside ``api_paths``.
"""

from __future__ import annotations

import uuid

from app.services.scan.backend_link import (
    BackendBucket,
    BackendIndex,
    bucket_per_repo,
)


def _index_with(repo_routes: dict[uuid.UUID, list[tuple[str, str]]]) -> BackendIndex:
    """Build a :class:`BackendIndex` from ``{repo_id: [(path, file), …]}``.

    Mirrors what :func:`build_index` produces — registers the path
    plus every contiguous suffix so a frontend URL with an unseen
    runtime prefix still resolves. Tests stay independent of the
    suffix-folding implementation by going through the public
    ``index.lookup``.
    """
    idx = BackendIndex()
    for repo_id, routes in repo_routes.items():
        for path, file_path in routes:
            idx.paths.setdefault(path, set()).add((repo_id, file_path))
            # All-suffixes registration matches the production helper.
            parts = [p for p in path.split("/") if p]
            for i in range(len(parts)):
                suffix = "/" + "/".join(parts[i:])
                idx.suffix_paths.setdefault(suffix, set()).add((repo_id, file_path))
    return idx


def test_one_path_one_repo_returns_path_and_file() -> None:
    """The simplest happy path: one matching api_path, one declaring backend."""
    repo = uuid.uuid4()
    idx = _index_with({repo: [("/api/users", "src/controllers/users.ts")]})

    buckets = bucket_per_repo(["/api/users"], idx)

    assert list(buckets.keys()) == [repo]
    bucket = buckets[repo]
    assert isinstance(bucket, BackendBucket)
    assert bucket.api_paths == ["/api/users"]
    assert bucket.code_locations == {"backend": ["src/controllers/users.ts"]}


def test_multi_path_multi_repo_keys_correctly() -> None:
    """Distinct backends each get their own bucket with their own files."""
    backend_a = uuid.uuid4()
    backend_b = uuid.uuid4()
    idx = _index_with(
        {
            backend_a: [("/api/users", "a/src/users.ts")],
            backend_b: [("/api/orders", "b/src/orders.ts")],
        }
    )

    buckets = bucket_per_repo(["/api/users", "/api/orders"], idx)

    assert buckets[backend_a].api_paths == ["/api/users"]
    assert buckets[backend_a].code_locations == {"backend": ["a/src/users.ts"]}
    assert buckets[backend_b].api_paths == ["/api/orders"]
    assert buckets[backend_b].code_locations == {"backend": ["b/src/orders.ts"]}


def test_dedupe_and_sort() -> None:
    """Repeated paths and out-of-order matches collapse to sorted, deduped output."""
    repo = uuid.uuid4()
    idx = _index_with(
        {
            repo: [
                ("/api/users", "src/users.ts"),
                ("/api/orders", "src/orders.ts"),
                # Same path declared twice from different files — both
                # files should land in code_locations, deduped + sorted.
                ("/api/users", "src/users-extra.ts"),
            ]
        }
    )

    # Caller hands the same api_path twice to test feature-side dedup.
    buckets = bucket_per_repo(["/api/orders", "/api/users", "/api/users"], idx)

    bucket = buckets[repo]
    assert bucket.api_paths == ["/api/orders", "/api/users"]
    assert bucket.code_locations == {
        "backend": ["src/orders.ts", "src/users-extra.ts", "src/users.ts"],
    }


def test_path_declared_by_two_backends_lands_in_both_buckets() -> None:
    """Cross-cutting routes legitimately live in both repos — emit both edges."""
    backend_a = uuid.uuid4()
    backend_b = uuid.uuid4()
    idx = _index_with(
        {
            backend_a: [("/api/health", "a/health.ts")],
            backend_b: [("/api/health", "b/health.ts")],
        }
    )

    buckets = bucket_per_repo(["/api/health"], idx)

    assert {backend_a, backend_b} == set(buckets.keys())
    assert buckets[backend_a].code_locations == {"backend": ["a/health.ts"]}
    assert buckets[backend_b].code_locations == {"backend": ["b/health.ts"]}


def test_no_match_returns_empty_dict() -> None:
    """An api_path with no index entry produces no buckets at all."""
    idx = _index_with({})
    buckets = bucket_per_repo(["/never/declared"], idx)
    assert buckets == {}
