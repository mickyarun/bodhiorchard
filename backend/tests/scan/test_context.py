# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tests for ``app.scan.context.ScanContext``.

The dataclass exists so phases are pure functions of an immutable
input. These tests pin that contract: frozen, default-friendly, and
the convenience predicate distinguishes per-repo from global scope.
"""

from __future__ import annotations

import dataclasses
import uuid

import pytest

from app.scan.context import ScanContext


def test_scan_context_is_frozen() -> None:
    """Phase bodies must not mutate context fields — frozen is the guarantee."""
    ctx = ScanContext(scan_id=uuid.uuid4(), org_id=uuid.uuid4())
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.repo_id = uuid.uuid4()  # type: ignore[misc]


def test_scan_context_global_scope_defaults() -> None:
    """A global-phase context has no repo fields populated."""
    ctx = ScanContext(scan_id=uuid.uuid4(), org_id=uuid.uuid4())
    assert ctx.is_per_repo is False
    assert ctx.repo_id is None
    assert ctx.repo_path is None
    assert ctx.repo_name is None
    assert ctx.sha is None
    assert ctx.full_rescan is False


def test_scan_context_per_repo_scope() -> None:
    """A per-repo context flips ``is_per_repo`` once ``repo_id`` is set."""
    ctx = ScanContext(
        scan_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        repo_path="/tmp/repo",
        repo_name="repo",
        sha="abc123",
    )
    assert ctx.is_per_repo is True
