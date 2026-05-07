# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tests for ``job_handlers`` worker-count defaults."""

from __future__ import annotations

from app.services.job_handlers import _design_extract_default_workers


def test_design_extract_defaults_to_one_worker() -> None:
    """Claude CLI subprocess is ~600MB; serialize by default to avoid OOM.

    Operators raise concurrency on beefy hosts via
    ``JOB_DESIGN_EXTRACT_WORKERS``.
    """
    assert _design_extract_default_workers() == 1
