# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Unit tests for the cross-phase audit DTOs.

The DB-level path (``audit_scan`` running real queries) is exercised
in live verification — these tests pin the value-object semantics so
future refactors can't quietly change the orchestrator's contract:

  - ``ScanAuditReport`` defaults to clean and ``is_clean`` reflects it.
  - Adding any anomaly category flips ``is_clean`` to False.
  - ``RepoAnomaly`` carries the four fields the orchestrator's log
    consumer expects (repo_id, repo_name, cluster_count, synth_count).
"""

from __future__ import annotations

import uuid

from app.scan.audit import RepoAnomaly, ScanAuditReport


def test_empty_report_is_clean() -> None:
    """Default-constructed report = healthy state. ``is_clean`` is True."""
    report = ScanAuditReport()
    assert report.is_clean is True
    assert report.missing_repo_synth == []
    assert report.orphan_features == []


def test_missing_repo_synth_flips_is_clean() -> None:
    """Any RepoAnomaly in missing_repo_synth flips is_clean to False."""
    anomaly = RepoAnomaly(
        repo_id=uuid.uuid4(),
        repo_name="ATOABatch",
        cluster_count=33,
        synth_count=0,
    )
    report = ScanAuditReport(missing_repo_synth=[anomaly])
    assert report.is_clean is False
    assert len(report.missing_repo_synth) == 1
    assert report.missing_repo_synth[0].cluster_count == 33


def test_orphan_features_flips_is_clean() -> None:
    """Any UUID in orphan_features flips is_clean to False."""
    report = ScanAuditReport(orphan_features=[uuid.uuid4()])
    assert report.is_clean is False


def test_repo_anomaly_carries_orchestrator_log_fields() -> None:
    """Pin the four fields the orchestrator's warning log uses.

    The log emits ``{name, clusters, synth}`` per anomaly — if any of
    those source fields disappear, the log breaks silently. This test
    guards the implicit shape contract.
    """
    anomaly = RepoAnomaly(
        repo_id=uuid.uuid4(),
        repo_name="AtoaIntegration",
        cluster_count=22,
        synth_count=0,
    )
    assert anomaly.repo_name == "AtoaIntegration"
    assert anomaly.cluster_count == 22
    assert anomaly.synth_count == 0
