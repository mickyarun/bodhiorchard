# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tests for the DB-backed ``scans`` table surface.

Covers the pure bits of the repo layer — the constant that gates
``get_latest_active``, the model ``__repr__``, and the schema
translation from ORM row to ``ScanStatus``. The DB-integration paths
(INSERT / UPDATE / RETURNING) are exercised end-to-end through the
scan pipeline; running them as unit tests against the shared
session-scoped ``db_session`` fixture deadlocks on asyncpg's
"another operation in progress" because our engine is singleton.
"""

from __future__ import annotations

import uuid

from app.models.scan import ACTIVE_SCAN_STATUSES, Scan, ScanAggregateStatus
from app.repositories.scan import _active_status_values
from app.services.scan_progress import _scan_to_status


def test_active_statuses_exclude_terminal() -> None:
    """``get_latest_active`` depends on this set omitting terminal states —
    otherwise a completed scan would mask a freshly-dispatched one."""
    assert ScanAggregateStatus.COMPLETED not in ACTIVE_SCAN_STATUSES
    assert ScanAggregateStatus.FAILED not in ACTIVE_SCAN_STATUSES
    # Sanity: the set is non-empty and contains the very first state.
    assert ScanAggregateStatus.STARTED in ACTIVE_SCAN_STATUSES


def test_active_status_values_is_string_list() -> None:
    """The SQL ``IN (...)`` clause wants plain strings, not enum members."""
    values = _active_status_values()
    assert "started" in values
    assert "completed" not in values
    assert all(isinstance(v, str) for v in values)


def test_scan_model_repr_has_status_and_id() -> None:
    """``__repr__`` shows up in structlog output; guard against typos."""
    row = Scan(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        org_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        status="analyzing_changes",
    )
    rendered = repr(row)
    assert "Scan(" in rendered
    assert "analyzing_changes" in rendered
    assert "00000000-0000-0000-0000-000000000001" in rendered


def test_scan_to_status_translates_known_fields() -> None:
    """The façade translates ORM rows to ``ScanStatus`` for the API.

    Captures the happy path — any column rename on ``Scan`` that
    forgets ``_scan_to_status`` surfaces here first.
    """
    row = Scan(
        id=uuid.UUID("00000000-0000-0000-0000-000000000099"),
        org_id=uuid.UUID("00000000-0000-0000-0000-0000000000aa"),
        parent_scan_id=uuid.UUID("00000000-0000-0000-0000-0000000000bb"),
        status="synthesizing_features",
        scan_mode="incremental",
        progress_pct=42,
        features_indexed=7,
        features_skipped=2,
        profiles_found=11,
        stale_cleaned=3,
        unmatched_authors=["alice@co", "bob@co"],
        synthesis_warning="partial sync",
        setup_pr_message="opened PR #14",
        error=None,
        repo_warnings=[{"repo": "r1", "phase": "B", "summary": "slow"}],
    )
    status = _scan_to_status(row)
    assert status.scan_id == "00000000-0000-0000-0000-000000000099"
    assert status.parent_scan_id == "00000000-0000-0000-0000-0000000000bb"
    assert status.status == "synthesizing_features"
    assert status.scan_mode == "incremental"
    assert status.progress_pct == 42
    assert status.features_indexed == 7
    assert status.unmatched_authors == ["alice@co", "bob@co"]
    assert status.synthesis_warning == "partial sync"
    assert len(status.repo_warnings) == 1
    assert status.repo_warnings[0].repo == "r1"


def test_scan_to_status_handles_null_optional_fields() -> None:
    """Null *text* columns translate to None.

    ``unmatched_authors`` / ``repo_warnings`` are NOT NULL with
    ``default=list``, so a freshly-constructed row has empty arrays,
    not None. The translator is exercised on the realistic initial
    shape the DB insert would produce.
    """
    row = Scan(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        org_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    )
    status = _scan_to_status(row)
    # Non-nullable defaults landed.
    assert status.unmatched_authors == []
    assert status.repo_warnings == []
    assert status.status == "started"
    assert status.progress_pct == 0
    # Nullable columns stay None.
    assert status.synthesis_warning is None
    assert status.setup_pr_message is None
    assert status.error is None
    assert status.parent_scan_id is None
