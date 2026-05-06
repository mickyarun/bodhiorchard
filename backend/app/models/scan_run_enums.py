# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Enums for the scan pipeline tables.

Kept in their own module so the scan ORM models can import them without
pulling in the legacy scan internals. Bound to PostgreSQL enum types
in the Alembic migration that creates ``scan_repo_runs`` and
``scan_repo_steps``.

Naming: enum values are stable identifiers persisted to the DB and
returned in the HTTP API. New values must only be added at the *end*
of the enum or via a follow-up migration that ALTERs the PG type.
"""

from enum import StrEnum


class RepoRunStatus(StrEnum):
    """Lifecycle state of a single ``scan_repo_runs`` row.

    A repo run is the per-repo unit of work in a scan: ingest →
    extract → ... → synthesize for one repository within one scan.
    """

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED_UNCHANGED = "skipped_unchanged"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    """Lifecycle state of a single ``scan_repo_steps`` row.

    A step corresponds to one ``ScanPhase`` execution within one repo
    run. ``SKIPPED_CACHE`` distinguishes "we deliberately reused a
    prior result" from ``SKIPPED`` ("intentionally not run, e.g.
    incremental-only phase").
    """

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED_CACHE = "skipped_cache"
    SKIPPED = "skipped"


class ScanKind(StrEnum):
    """Top-level shape of a scan.

    ``FULL`` scans every selected repo's pipeline end-to-end.
    ``INCREMENTAL`` reuses cached steps when the HEAD sha is unchanged.
    ``SINGLE_REPO`` is a one-off scan triggered from a per-repo card.
    """

    FULL = "full"
    INCREMENTAL = "incremental"
    SINGLE_REPO = "single_repo"
