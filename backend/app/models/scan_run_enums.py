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
