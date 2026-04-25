# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Scan pipeline package — phases, orchestration, audit.

This package replaces the legacy ``app.services.scan_*`` modules. The
migration happens stage-by-stage (see the plan file): foundations land
first, individual phases move in next, the audit consolidates last.

Public surface intentionally minimal — callers should import:
- ``ScanContext`` from ``app.scan.context``
- ``with_session`` / ``gather_repos`` from ``app.scan.session``

Phase modules under ``app.scan.per_repo`` and ``app.scan.global_`` are
internal to the package; the orchestrator wires them together.
"""
