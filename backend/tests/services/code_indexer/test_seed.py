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

# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Tests for ``app.services.code_indexer.seed``."""

from __future__ import annotations

from app.services.code_indexer.seed import (
    head_sha_seed,
    order_partition,
    stable_cluster_id,
)


def test_stable_cluster_id_format() -> None:
    assert stable_cluster_id(0) == "c0"
    assert stable_cluster_id(42) == "c42"


def test_seed_zero_for_missing_sha() -> None:
    assert head_sha_seed(None) == 0
    assert head_sha_seed("") == 0


def test_seed_deterministic() -> None:
    sha = "abc123def456" * 4
    assert head_sha_seed(sha) == head_sha_seed(sha)


def test_seed_changes_for_different_sha() -> None:
    a = head_sha_seed("aaa" * 14)
    b = head_sha_seed("bbb" * 14)
    assert a != b


def test_order_largest_first() -> None:
    partition = {3: ["x"], 1: ["a", "b", "c"], 7: ["a", "b"]}
    out = order_partition(partition, head_sha=None)
    sizes = [len(members) for _, members in out]
    assert sizes == sorted(sizes, reverse=True)


def test_order_assigns_canonical_ids_starting_at_zero() -> None:
    partition = {99: ["a", "b"], 7: ["x"]}
    out = order_partition(partition, head_sha=None)
    ids = [cid for cid, _ in out]
    assert ids == ["c0", "c1"]


def test_order_deterministic_for_same_sha() -> None:
    partition = {0: ["a", "b"], 1: ["c", "d"]}
    a = order_partition(partition, head_sha="deadbeef" * 5)
    b = order_partition(partition, head_sha="deadbeef" * 5)
    assert a == b


def test_order_tiebreak_uses_min_member_id() -> None:
    """Two equal-size clusters: smaller min member id sorts first."""
    partition = {0: ["zeta", "yankee"], 1: ["alpha", "bravo"]}
    out = order_partition(partition, head_sha=None)
    # Cluster containing "alpha" comes first because min("alpha","bravo") < min("yankee","zeta")
    assert "alpha" in out[0][1]
