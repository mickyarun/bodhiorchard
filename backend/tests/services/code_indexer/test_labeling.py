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

"""Tests for ``app.services.code_indexer.labeling``."""

from __future__ import annotations

from app.services.code_indexer.labeling import (
    extract_path_tokens,
    extract_text_tokens,
    label_cluster,
)


def test_picks_distinctive_domain_token() -> None:
    cluster_files = [
        "src/services/ais/AisSdkService.ts",
        "src/controllers/api/ais/AisRedirectController.ts",
        "src/repository/ais/AisConsentRepository.ts",
    ]
    corpus = cluster_files + [
        "src/services/auth/AuthService.ts",
        "src/services/payments/PaymentsService.ts",
    ]
    assert label_cluster(cluster_files, corpus_files=corpus) == "ais"


def test_drops_blocked_infrastructure_tokens() -> None:
    cluster_files = [
        "src/services/something/Service.ts",
        "src/services/something/Helper.ts",
    ]
    label = label_cluster(cluster_files)
    # The label is one of the meaningful tokens, never a blocked one.
    assert label not in {"src", "services", "ts"}
    assert label == "something"


def test_kebab_compounds_camelcase_token() -> None:
    cluster_files = [
        "src/bankFeed/BankFeedService.ts",
        "src/bankFeed/BankFeedRepository.ts",
        "src/bankFeed/BankFeedController.ts",
    ]
    label = label_cluster(cluster_files)
    # Per-segment compound emission means ``bank-feed`` outscores its parts
    # when the segment carries both tokens — keeps the domain noun intact for
    # the synthesis prompt.
    assert label == "bank-feed"


def test_compound_token_beats_single_token_on_tie() -> None:
    # Regression: when a compound camelCase directory like ``orderShipment``
    # splits into two single tokens (``order`` + ``shipment``), the bare
    # halves can collide with unrelated single-domain clusters in the
    # synthesis prompt's JSON payload. The per-segment compound restores
    # the two-word domain noun so the label remains unambiguous.
    cluster_files = [
        "src/services/orderShipment/OrderShipmentService.ts",
        "src/services/orderShipment/OrderShipmentServiceBatch.ts",
        "src/controllers/api/orderShipment/OrderShipmentController.ts",
        "src/repository/orderShipment/OrderShipmentRepository.ts",
    ]
    corpus = cluster_files + [
        "src/services/inventory/InventoryService.ts",
        "src/services/billing/BillingService.ts",
        "src/services/order/OrderService.ts",
    ]
    assert label_cluster(cluster_files, corpus_files=corpus) == "order-shipment"


def test_falls_back_when_cluster_empty() -> None:
    assert label_cluster([], fallback="unknown") == "unknown"


def test_extract_text_tokens_handles_punctuated_titles() -> None:
    # Feature titles in the wild carry parentheses, slashes, version
    # markers — the tokeniser should reduce them to the same vocabulary
    # the path extractor produces so the domain-overlap guard can compare
    # them on equal terms.
    tokens = extract_text_tokens("Inventory (Stock & Catalog) Management")
    assert "inventory" in tokens
    assert "management" in tokens
    assert "catalog" in tokens
    assert "stock" in tokens
    assert "(" not in "".join(tokens)


def test_extract_path_tokens_emits_compound_bigrams() -> None:
    tokens = extract_path_tokens(
        ["src/controllers/api/orderShipment/OrderShipmentController.ts"],
    )
    assert "order-shipment" in tokens
    assert "order" in tokens
    assert "shipment" in tokens
    # Blocked infrastructure stays out.
    assert "controllers" not in tokens
    assert "ts" not in tokens


def test_deterministic_across_runs() -> None:
    files = [
        "src/services/payments/Foo.ts",
        "src/services/payments/Bar.ts",
        "src/services/payments/Baz.ts",
    ]
    a = label_cluster(files)
    b = label_cluster(files)
    assert a == b
    assert a == "payments"
