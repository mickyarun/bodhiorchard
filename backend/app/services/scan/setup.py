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

"""Helpers that prepare a scan before the per-repo workflow fires.

Pulled out of ``scan_runner.py`` so that file stays under the size
budget and only owns the orchestration loop. This module covers:

* :class:`RepoDescriptor` — frozen snapshot the per-repo background
  task closes over.
* :func:`load_repo_descriptor` — resolve `(name, path, head_sha)` for
  one tracked repo.
* :func:`create_scan_rows` — POST /scans entry: insert the ``Scan``
  row + one ``ScanRepoRun`` per selected repo, captured before the
  fanout starts.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import structlog

from app.models.scan import Scan, ScanAggregateStatus
from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.repositories.scan_run import ScanRunRepository
from app.scan.session import with_session
from app.services.git_operations import run_git

logger = structlog.get_logger(__name__)


class RepoDescriptor:
    """Frozen snapshot of repo state captured at scan start."""

    __slots__ = ("repo_id", "repo_name", "repo_path", "head_sha", "main_branch")

    def __init__(
        self,
        *,
        repo_id: uuid.UUID,
        repo_name: str,
        repo_path: str,
        head_sha: str | None,
        main_branch: str | None,
    ) -> None:
        self.repo_id = repo_id
        self.repo_name = repo_name
        self.repo_path = repo_path
        self.head_sha = head_sha
        # User-selected primary branch, captured by the wizard and stored
        # on ``TrackedRepository``. Threaded into the ingest stage's
        # config so it doesn't fall back to detecting ``origin/HEAD``,
        # which can point at a feature branch on imported GitHub repos.
        self.main_branch = main_branch


async def load_repo_descriptor(db: Any, repo_id: uuid.UUID) -> RepoDescriptor | None:
    """Resolve `(name, path, head_sha)` for one tracked repo.

    Returns ``None`` for unknown ids and for soft-deleted (``REMOVED``)
    rows. The caller's loop logs ``scan_skip_unknown_repo`` and continues,
    so a stale ``repo_id`` left over from a frontend cache won't drag a
    removed repo back into the scan.
    """
    tracked = await db.get(TrackedRepository, repo_id)
    if tracked is None or tracked.status == RepoStatus.REMOVED:
        return None
    head_sha = await read_head_sha(tracked.path)
    return RepoDescriptor(
        repo_id=tracked.id,
        repo_name=tracked.name,
        repo_path=tracked.path,
        head_sha=head_sha,
        main_branch=tracked.main_branch,
    )


async def read_head_sha(repo_path: str) -> str | None:
    """``git rev-parse HEAD`` against the local clone, no-throw."""
    if not Path(repo_path).exists():
        return None
    stdout, _, rc = await run_git(["rev-parse", "HEAD"], cwd=repo_path)
    if rc != 0:
        return None
    return stdout.strip() or None


async def create_scan_rows(
    *,
    org_id: uuid.UUID,
    repo_ids: list[uuid.UUID],
    full_rescan: bool = False,
) -> tuple[uuid.UUID, list[RepoDescriptor]]:
    """Create the Scan + one ScanRepoRun per repo. Returns (scan_id, descriptors).

    ``full_rescan`` only labels the row's ``scan_mode`` column so the UI
    can distinguish a forced full rescan from an incremental one. The
    actual skip-unchanged behavior is gated by the same flag inside
    ``_check_skip_unchanged`` — this just keeps the DB label honest.
    """
    descriptors: list[RepoDescriptor] = []
    async with with_session(org_id) as db:
        scan = Scan(
            org_id=org_id,
            status=ScanAggregateStatus.STARTED.value,
            scan_mode="full" if full_rescan else "incremental",
        )
        db.add(scan)
        await db.flush()
        run_repo = ScanRunRepository(db, org_id=org_id)
        for repo_id in repo_ids:
            descriptor = await load_repo_descriptor(db, repo_id)
            if descriptor is None:
                logger.warning("scan_skip_unknown_repo", repo_id=str(repo_id))
                continue
            await run_repo.upsert_repo_run(
                scan_id=scan.id,
                repo_id=repo_id,
                head_sha_at_start=descriptor.head_sha,
            )
            descriptors.append(descriptor)
        await db.commit()
        return scan.id, descriptors
