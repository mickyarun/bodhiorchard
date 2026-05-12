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

"""Tests for the domain-overlap guard in ``handlers_scan``.

Covers the regression where the LLM lumped clusters from an unrelated
domain (e.g. a refund pipeline) under a feature describing a different
domain (e.g. identity verification) because the clusters' single-word
labels happened to be ambiguous in the synthesis prompt. The guard
rejects a cluster — or an LLM-supplied file path — from the file union
when its vocabulary shares zero tokens with the feature title +
description.

Fixtures use abstract domain nouns (``inventory``, ``orderShipment``,
``billing``) so the test reads as a pattern, not as a customer-specific
codebase.
"""

from __future__ import annotations

from app.mcp.handlers_scan import _cluster_overlaps_feature, _path_overlaps_feature
from app.services.code_indexer.labeling import extract_text_tokens


def test_drops_cluster_when_no_domain_overlap() -> None:
    # Feature describes inventory management; cluster contains shipment
    # controllers — zero shared tokens, so the guard must reject the
    # cluster from this feature's file union.
    feature_tokens = extract_text_tokens(
        "Inventory Management — adjust stock levels, catalog updates, low-stock alerts"
    )
    unrelated_cluster_files = [
        "src/controllers/api/orderShipment/OrderShipmentController.spec.ts",
        "src/controllers/api/orderShipment/OrderShipmentController.ts",
    ]
    assert _cluster_overlaps_feature(unrelated_cluster_files, feature_tokens) is False


def test_keeps_cluster_when_path_token_appears_in_title() -> None:
    feature_tokens = extract_text_tokens("Inventory Reconciliation")
    inventory_files = [
        "src/services/inventory/InventoryService.ts",
        "src/controllers/api/inventory/InventoryController.ts",
    ]
    assert _cluster_overlaps_feature(inventory_files, feature_tokens) is True


def test_keeps_cluster_when_match_is_via_description_only() -> None:
    # Title says nothing about the path noun; description does. The guard
    # must read both so legitimate features with creative titles don't get
    # their backing clusters falsely rejected.
    feature_tokens = extract_text_tokens(
        "Stock Pulse — internal inventory service tracking item levels per warehouse"
    )
    inventory_files = ["src/services/inventory/InventoryService.ts"]
    assert _cluster_overlaps_feature(inventory_files, feature_tokens) is True


def test_no_signal_does_not_reject() -> None:
    # Missing feature text or empty cluster files → don't suppress data.
    assert _cluster_overlaps_feature(["src/foo/bar.ts"], set()) is True
    assert _cluster_overlaps_feature([], {"inventory"}) is True
    assert _cluster_overlaps_feature(None, {"inventory"}) is True


def test_per_file_guard_flags_orphan_path() -> None:
    # The per-file guard is a *decision predicate*: True when the path
    # overlaps the feature text, False otherwise. The handler runs in
    # log-only mode for LLM-supplied paths (the model's direct output is
    # treated as intent, never dropped) — so the predicate is used to
    # emit ``synth_feature_file_no_domain_overlap`` telemetry while the
    # file itself is still kept in ``code_locations``.
    feature_tokens = extract_text_tokens(
        "Inventory Management — adjust stock levels and run catalog updates"
    )
    assert (
        _path_overlaps_feature(
            "src/controllers/api/orderShipment/OrderShipmentController.ts",
            feature_tokens,
        )
        is False
    )


def test_per_file_guard_keeps_in_domain_path() -> None:
    feature_tokens = extract_text_tokens("Inventory Management")
    assert (
        _path_overlaps_feature("src/services/inventory/InventoryService.ts", feature_tokens)
        is True
    )
