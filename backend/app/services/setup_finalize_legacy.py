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

"""Local-path arm of the wizard's stage-2 finalize.

Pulled into its own module so :mod:`setup_finalize` stays well under
the project's 200-line ceiling. Each configured local path is
upserted as a tracked repo, its branch mapping is applied, and the
shared :func:`kick_off_onboard_scan` helper is invoked once with the
surviving repo IDs — the same seam used by the GitHub-App bulk
onboard.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.organization import Organization
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.setup import SetupSourceCode
from app.services.directory_listing import in_clone_root, picker_roots
from app.services.scan_kickoff import kick_off_onboard_scan

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class LegacyFinalizeResult:
    """Outcome of the legacy finalize path — scan kickoff + warnings."""

    scan_id: str | None
    embedding_warning: str | None


async def finalize_legacy_source_code(
    *,
    org: Organization,
    source_code: SetupSourceCode,
    db: AsyncSession,
) -> LegacyFinalizeResult:
    """Register pre-cloned repos and synchronously trigger a scan.

    Returns the new scan_id (or ``None`` if the embedding service is
    down — in which case a warning is surfaced for the wizard to
    display). Idempotent through ``TrackedRepoRepository.upsert``;
    calling this twice with the same paths re-uses existing rows
    rather than creating duplicates.

    Paths are held to the bar of ``POST /settings/repos``: under a
    :func:`picker_roots` root and outside the shared clone root, which
    holds every org's clones side by side. One part of the clone root is
    allowed, the org's own ``<repos_dir>/<slug>``, because the wizard's
    GitHub-clone tab lists its clones here to get them scanned. A path
    that fails is skipped like any other unusable entry.
    """
    repo_repo = TrackedRepoRepository(db, org_id=org.id)
    valid_repo_ids: list[uuid.UUID] = []
    own_clones = os.path.realpath(str(settings.storage.repos_dir / org.slug))

    for repo_cfg in source_code.repos:
        # Containment check, inline and on the raw string — see
        # :func:`settings_repos_local.browse_directories` for why it cannot
        # move into a helper.
        candidate = os.path.realpath(os.path.expanduser(repo_cfg.path))
        within = False
        for root in picker_roots():
            base = os.path.realpath(str(root))
            try:
                within = os.path.commonpath([base, candidate]) == base
            except ValueError:
                within = False  # unrelated roots / different drives
            if within:
                break
        # The org's own clones are the one exception to the clone-root
        # deny (the wizard sends them back after a GitHub clone). The
        # allow side stays exact, so case can only ever over-refuse.
        try:
            own_clone = os.path.commonpath([own_clones, candidate]) == own_clones
        except ValueError:
            own_clone = False
        if not own_clone and (not within or in_clone_root(candidate)):
            logger.warning("setup_skip_repo_outside_roots", path=candidate, org_id=str(org.id))
            continue
        repo_path = Path(candidate)
        # os.path, not Path: a name too long for the filesystem reads as
        # missing (and is skipped) instead of failing the whole batch.
        if not os.path.exists(repo_path / ".git"):
            logger.warning("setup_skip_invalid_repo", path=str(repo_path))
            continue

        tracked = await repo_repo.upsert(str(repo_path), repo_path.name)
        valid_repo_ids.append(tracked.id)

        if repo_cfg.main_branch:
            tracked.main_branch = repo_cfg.main_branch
        if repo_cfg.develop_branch:
            tracked.develop_branch = repo_cfg.develop_branch

    await db.flush()
    # Commit before kicking off the scan: the kickoff opens its own
    # AsyncSessionLocal and reads these freshly-created rows.
    await db.commit()

    new_scan_id, embedding_warning = await kick_off_onboard_scan(
        org_id=org.id,
        repo_ids=valid_repo_ids,
    )
    scan_id_str = str(new_scan_id) if new_scan_id is not None else None
    if scan_id_str is not None:
        logger.info(
            "setup_finalize_legacy_scan_triggered",
            scan_id=scan_id_str,
            repos=len(valid_repo_ids),
        )
    return LegacyFinalizeResult(scan_id=scan_id_str, embedding_warning=embedding_warning)
