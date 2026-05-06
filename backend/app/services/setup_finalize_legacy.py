# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Local-path arm of the wizard's stage-2 finalize.

Pulled into its own module so :mod:`setup_finalize` stays well under
the project's 200-line ceiling. Each configured local path is
upserted as a tracked repo, its branch mapping is applied, and the
shared :func:`kick_off_onboard_scan` helper is invoked once with the
surviving repo IDs — the same seam used by the GitHub-App bulk
onboard.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.setup import SetupSourceCode
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
    """
    repo_repo = TrackedRepoRepository(db, org_id=org.id)
    valid_repo_ids: list[uuid.UUID] = []

    for repo_cfg in source_code.repos:
        repo_path = Path(repo_cfg.path).resolve()
        if not repo_path.exists() or not (repo_path / ".git").exists():
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
