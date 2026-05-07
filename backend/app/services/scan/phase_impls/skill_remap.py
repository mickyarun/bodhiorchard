# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Phase E2 — re-run skill analysis with feature-based modules.

On a full scan Phase E (per-repo) populates ``skill_profiles`` keyed
by directory module (``lib``, ``android``, …) because no features
exist yet. Once Phase B2 has synthesised features and Phase B3 has
merged them, the feature map is rich enough to re-run the same
git-log analysis with feature names as modules.

This phase walks each repo's git log a second time with the feature
map loaded, then either wipes-and-reinserts (when the new analysis
covers ≥ 70% of the existing profile count) or does a partial update
(when the map is sparse). The 70% threshold prevents a sparse merge
from nuking a mature directory-based profile set built up over many
scans — the partial update keeps the unmatched rows live and only
upgrades the ones that matched a feature.

The wipe-and-reinsert is wrapped in ``begin_nested`` so a crash
between DELETE and INSERT rolls back cleanly. Before that guard, a
failed upsert after the delete left the org with zero skill profiles
until the next successful scan.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.git_analyzer import analyze_repo_skills
from app.services.scan_helpers import load_feature_map, upsert_skill_profiles

logger = structlog.get_logger(__name__)


# Minimum ratio of new-analysis entries vs. existing profile rows below
# which SKILL_REMAP falls back to a partial update instead of a full
# wipe-and-replace. Prevents a sparse feature map from erasing a mature
# directory-based profile set when only a handful of features synthesise.
_E2_SPARSE_THRESHOLD = 0.7


async def phase_e2_skill_remap(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_paths: list[str],
    email_to_user: dict[str, User],
    scan_id: str,
) -> int:
    """Phase E2: Re-run skill analysis with feature-based modules.

    On full scans, Phase E ran before features existed. Now that
    features are synthesized, reload the feature map and rebuild
    skill profiles so modules are feature names, not directories.

    Only wipes old profiles if the new feature-based analysis covers
    at least 70% of the old profile count, to avoid data loss when
    the feature map is sparse (Bug 6 fix).

    Args:
        db: Async database session.
        org_id: Organization UUID.
        repo_paths: List of all repo paths being scanned.
        email_to_user: Mapping of lowercase email → User.
        scan_id: Scan identifier for progress tracking.

    Returns:
        Total profiles upserted.
    """
    from app.repositories.skill_profile import SkillProfileRepository
    from app.services.scan_progress import update_scan_progress

    feature_map_e2 = await load_feature_map(db, org_id)
    if not feature_map_e2:
        return 0

    await update_scan_progress(
        scan_id,
        status="remapping_skills",
        progress_pct=92,
    )
    sp_repo_e2 = SkillProfileRepository(db, org_id=org_id)

    # Run new analysis first (before deleting anything).
    new_entries = []
    for repo_path_e2 in repo_paths:
        entries_e2 = await analyze_repo_skills(repo_path_e2, feature_map=feature_map_e2)
        new_entries.extend(entries_e2)

    existing_count = await sp_repo_e2.count_profiles()

    # Only wipe+replace if new analysis has good coverage. Below the
    # threshold we fall back to a partial update so the sparse feature
    # map doesn't nuke well-established directory-based profiles.
    if not existing_count or len(new_entries) >= existing_count * _E2_SPARSE_THRESHOLD:
        # Wrap DELETE + INSERT in a SAVEPOINT so a crash between them
        # rolls back cleanly — the old skill_profiles rows stay intact
        # until the new ones are fully in place. Before this guard, a
        # failed upsert after the delete left the org with zero skill
        # profiles until the next successful scan.
        async with db.begin_nested():
            deleted_profiles = await sp_repo_e2.delete_all_for_org()
            if deleted_profiles:
                logger.info("e2_deleted_old_profiles", count=deleted_profiles)
            count, _ = await upsert_skill_profiles(db, org_id, new_entries, email_to_user)
        total_profiles = count
    else:
        # Sparse feature map — update feature_ids on matching profiles
        # without wiping unmatched ones.
        logger.warning(
            "e2_sparse_map_partial_update",
            new_entries=len(new_entries),
            existing=existing_count,
        )
        count, _ = await upsert_skill_profiles(db, org_id, new_entries, email_to_user)
        total_profiles = existing_count

    return total_profiles
