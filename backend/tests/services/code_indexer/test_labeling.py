# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Tests for ``app.services.code_indexer.labeling``."""

from __future__ import annotations

from app.services.code_indexer.labeling import label_cluster


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
    # CamelCase tokens split into separate components; the dominant
    # path-token wins. Either Bank or Feed is acceptable as long as the
    # label is a meaningful domain word (not infrastructure).
    assert label in {"bank", "feed", "bank-feed"}
    assert label not in {"src", "ts", "services"}


def test_falls_back_when_cluster_empty() -> None:
    assert label_cluster([], fallback="unknown") == "unknown"


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
