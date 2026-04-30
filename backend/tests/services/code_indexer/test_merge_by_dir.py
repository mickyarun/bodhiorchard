# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Tests for ``app.services.code_indexer.merge_by_dir``."""

from __future__ import annotations

from app.services.code_indexer.merge_by_dir import merge_clusters_by_directory


def _node_to_file(items: dict[str, str]) -> dict[str, str]:
    return dict(items)


def test_collapses_same_directory_clusters() -> None:
    partition = {0: ["n1"], 1: ["n2"], 2: ["n3"]}
    nodes = _node_to_file(
        {
            "n1": "src/services/ais/AisFoo.ts",
            "n2": "src/services/ais/AisBar.ts",
            "n3": "src/services/ais/AisBaz.ts",
        }
    )
    out = merge_clusters_by_directory(partition, nodes)
    assert len(out) == 1
    assert sorted(out[0]) == ["n1", "n2", "n3"]


def test_keeps_different_directories_separate() -> None:
    partition = {0: ["a", "b", "c", "d"]}
    nodes = _node_to_file(
        {
            "a": "src/services/ais/Foo.ts",
            "b": "src/services/ais/Bar.ts",
            "c": "src/services/payments/Pay.ts",
            "d": "src/services/payments/Charge.ts",
        }
    )
    out = merge_clusters_by_directory(partition, nodes)
    assert len(out) == 2
    flattened = sorted([sorted(v) for v in out.values()])
    assert flattened == [["a", "b"], ["c", "d"]]


def test_empty_partition_returns_empty_dict() -> None:
    assert merge_clusters_by_directory({}, {}) == {}


def test_no_source_file_nodes_remain_in_singleton_buckets() -> None:
    partition = {0: ["x", "y"], 1: ["z"]}
    nodes = _node_to_file({})  # no source_file mappings
    out = merge_clusters_by_directory(partition, nodes)
    # Each original cluster's no-file nodes get their own bucket.
    assert len(out) == 2
    flattened = sorted([sorted(v) for v in out.values()])
    assert flattened == [["x", "y"], ["z"]]


def test_root_files_stay_separate_after_fix() -> None:
    """Bug-fix regression: README.md and package.json must NOT merge."""
    partition = {0: ["a", "b"]}
    nodes = _node_to_file({"a": "README.md", "b": "package.json"})
    out = merge_clusters_by_directory(partition, nodes)
    assert len(out) == 2
    assert sorted([sorted(v) for v in out.values()]) == [["a"], ["b"]]


def test_dir_depth_caps_at_three_by_default() -> None:
    partition = {0: ["a", "b"]}
    nodes = _node_to_file(
        {
            "a": "src/services/ais/sub/deep/Foo.ts",
            "b": "src/services/ais/sub/other/Bar.ts",
        }
    )
    out = merge_clusters_by_directory(partition, nodes)
    # Both are under src/services/ais (depth=3) so they merge.
    assert len(out) == 1


def test_dir_depth_override_keeps_subdirs_separate() -> None:
    partition = {0: ["a", "b"]}
    nodes = _node_to_file(
        {
            "a": "src/services/ais/sandbox/Foo.ts",
            "b": "src/services/ais/sdk/Bar.ts",
        }
    )
    out = merge_clusters_by_directory(partition, nodes, dir_depth=4)
    assert len(out) == 2


def test_jvm_deep_package_uses_feature_segment() -> None:
    """Maven/Gradle layout: depth-3 must reach feature namespace, not collapse."""
    partition = {0: ["a", "b", "c"]}
    nodes = {
        "a": "src/main/java/com/example/auth/AuthService.java",
        "b": "src/main/java/com/example/auth/AuthRepository.java",
        "c": "src/main/java/com/example/payments/PaymentService.java",
    }
    out = merge_clusters_by_directory(partition, nodes)
    # ``auth`` and ``payments`` should each get their own bucket
    assert len(out) == 2


def test_android_studio_layout_splits_by_feature() -> None:
    partition = {0: ["a", "b"]}
    nodes = {
        "a": "app/src/main/kotlin/io/bodhi/wallet/WalletViewModel.kt",
        "b": "app/src/main/kotlin/io/bodhi/transactions/TransactionsViewModel.kt",
    }
    out = merge_clusters_by_directory(partition, nodes)
    assert len(out) == 2


def test_non_jvm_layouts_unchanged() -> None:
    """Regression guard: TS/Python/Go/Ruby layouts must keep their existing semantics."""
    partition = {0: ["a", "b"]}
    nodes = {
        "a": "src/services/ais/AisFoo.ts",
        "b": "src/services/ais/AisBar.ts",
    }
    out = merge_clusters_by_directory(partition, nodes)
    assert len(out) == 1


def test_largest_buckets_first() -> None:
    partition = {0: ["a", "b", "c", "d", "e"]}
    nodes = _node_to_file(
        {
            "a": "src/services/big/A.ts",
            "b": "src/services/big/B.ts",
            "c": "src/services/big/C.ts",
            "d": "src/services/small/X.ts",
            "e": "src/services/small/Y.ts",
        }
    )
    out = merge_clusters_by_directory(partition, nodes)
    assert len(out) == 2
    assert len(out[0]) == 3  # big bucket first
    assert len(out[1]) == 2
