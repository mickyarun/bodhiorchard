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


def test_layer_dir_recurses_into_per_domain_buckets() -> None:
    """``src/controllers/api/<domain>/`` is the ATOACore failure shape.

    With the old single-pass depth=3 logic every controller domain
    collapsed into one mega-cluster keyed at ``src/controllers/api``.
    The fan-out trigger should now split it per domain at depth=4.
    """
    domains = [
        "ais",
        "auth",
        "merchant",
        "business",
        "user",
        "payments",
        "invoice",
        "appConfig",
    ]
    partition: dict[int, list[str]] = {0: []}
    nodes: dict[str, str] = {}
    # 8 domains × 4 suffixes = 32 files — above ``_RECURSE_MIN_FILES`` (30).
    # 4 files per domain so each sub-bucket is "meaningful" (≥ 2 each).
    counter = 0
    for d in domains:
        for suffix in ("Controller.ts", "Controller.spec.ts", "Routes.ts", "Routes.spec.ts"):
            nid = f"n{counter}"
            counter += 1
            nodes[nid] = f"src/controllers/api/{d}/{d.capitalize()}{suffix}"
            partition[0].append(nid)

    out = merge_clusters_by_directory(partition, nodes)
    # 8 domains, each its own bucket
    assert len(out) == 8


def test_layer_dir_below_recurse_floor_stays_collapsed() -> None:
    """Small ``controllers/api`` (under 30 files) keeps the old behaviour.

    Recursion is only worth it on substantial layers; tiny ones aren't
    actually wedging multi-domain content together.
    """
    partition: dict[int, list[str]] = {0: []}
    nodes: dict[str, str] = {}
    for i, d in enumerate(["ais", "auth", "merchant"]):
        nid = f"n{i}"
        nodes[nid] = f"src/controllers/api/{d}/Foo.ts"
        partition[0].append(nid)
    out = merge_clusters_by_directory(partition, nodes)
    # Below the 30-file floor → one bucket at depth=3 as before.
    assert len(out) == 1


def test_domain_dir_with_few_subfolders_does_not_recurse() -> None:
    """``src/services/payments/`` with many files in 1-2 child folders
    must NOT split — that's a real domain, not a layer.
    """
    partition: dict[int, list[str]] = {0: []}
    nodes: dict[str, str] = {}
    # 40 files split into just 2 child folders → fan-out 2 < 5 → no recurse
    for i in range(20):
        nodes[f"a{i}"] = f"src/services/payments/core/File{i}.ts"
        partition[0].append(f"a{i}")
    for i in range(20):
        nodes[f"b{i}"] = f"src/services/payments/helpers/File{i}.ts"
        partition[0].append(f"b{i}")
    out = merge_clusters_by_directory(partition, nodes)
    assert len(out) == 1


def test_recurse_min_files_kwarg_lets_smaller_layer_dirs_split() -> None:
    """A 25-file ``controllers/api/`` across 6 domains stays mega-clustered
    at the default ``recurse_min_files=30`` — but lowering the kwarg
    triggers the per-domain split. Lets callers tune for repos whose
    layer dirs are smaller than ATOACore's.
    """
    partition: dict[int, list[str]] = {0: []}
    nodes: dict[str, str] = {}
    # 24 files: 6 domains × 4 files. Each domain has ≥ 2 files (meets
    # the meaningful-subbucket bar) but the *bucket* total is below 30.
    counter = 0
    for d in ["a", "b", "c", "d", "e", "f"]:
        for i in range(4):
            nid = f"n{counter}"
            counter += 1
            nodes[nid] = f"src/controllers/api/{d}/Foo{i}.ts"
            partition[0].append(nid)

    out_default = merge_clusters_by_directory(partition, nodes)
    # Default thresholds → mega-cluster (one bucket of 24 at depth=3).
    assert len(out_default) == 1

    out_tuned = merge_clusters_by_directory(partition, nodes, recurse_min_files=20)
    # Tuned threshold lowered → recursion triggers, each domain its own bucket.
    assert len(out_tuned) == 6


def test_recursion_capped_at_max_depth() -> None:
    """Pathologically nested layer dirs stop splitting at the depth ceiling."""
    partition: dict[int, list[str]] = {0: []}
    nodes: dict[str, str] = {}
    # 6 distinct child segments at depth 7, 6 files each → would recurse forever
    # without the cap. ``max_depth=4`` clamps it after one split.
    for d in range(6):
        for i in range(6):
            nid = f"d{d}f{i}"
            nodes[nid] = f"a/b/c/d/e/f/seg{d}/Foo{i}.ts"
            partition[0].append(nid)
    out = merge_clusters_by_directory(partition, nodes, max_depth=4)
    # All 36 files end up in one bucket because depth=3 returns 'a/b/c'
    # and we cap before reaching the seg<N> segment.
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
