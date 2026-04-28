# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Reusable helpers for the scan pipeline.

Contains timing utilities, the skill-profile upsert loop (used by both
Phase E and Phase E2), and helper functions extracted from the pipeline.
"""

import re
import time
import uuid

import structlog
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill_profile import SkillProfile
from app.models.user import User
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.skill_profile import SkillProfileRepository
from app.services.embedding_service import embedding_service
from app.services.git_analyzer import DevSkillEntry, FeatureMap
from app.utils.code_locations import merge_code_locations

logger = structlog.get_logger(__name__)


class PhaseTimer:
    """Lightweight timer that replaces the repeated ``phase_t0 / _mark()`` pattern.

    Usage::

        timer = PhaseTimer(scan_id)
        timer.start()
        # ... do work ...
        timer.mark("A_scan_mode/repo")
    """

    def __init__(self, scan_id: str) -> None:
        self.scan_id = scan_id
        self.timings: dict[str, float] = {}
        self._t0: float = 0.0

    def start(self) -> None:
        """Record the start time for the next phase."""
        self._t0 = time.monotonic()

    def mark(self, phase: str) -> None:
        """Record elapsed time since last ``start()`` and log it."""
        elapsed = round(time.monotonic() - self._t0, 1)
        self.timings[phase] = elapsed
        logger.info("scan_phase_done", scan_id=self.scan_id, phase=phase, elapsed_s=elapsed)


async def upsert_skill_profiles(
    db: AsyncSession,
    org_id: uuid.UUID,
    skill_entries: list[DevSkillEntry],
    email_to_user: dict[str, User],
) -> tuple[int, list[str]]:
    """Create or update skill profiles from git skill analysis entries.

    This logic was duplicated in Phase E and Phase E2 of the scan pipeline.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        skill_entries: Skill entries from ``analyze_repo_skills()``.
        email_to_user: Mapping of lowercase email → User.

    Returns:
        Tuple of (profiles_upserted, unmatched_emails).
    """
    sp_repo = SkillProfileRepository(db, org_id=org_id)
    count = 0
    unmatched: list[str] = []

    for entry in skill_entries:
        user = email_to_user.get(entry.email.lower())
        if user is None:
            if entry.email not in unmatched:
                unmatched.append(entry.email)
            continue

        count += 1
        profile = await sp_repo.get_by_user_and_module(user.id, entry.module)

        if profile:
            profile.touch_count = entry.touch_count
            profile.skill_score = entry.skill_score
            profile.languages = entry.languages
            profile.last_touch = entry.last_touch
            profile.feature_id = entry.feature_id
        else:
            profile = SkillProfile(
                user_id=user.id,
                org_id=org_id,
                module=entry.module,
                feature_id=entry.feature_id,
                languages=entry.languages,
                skill_score=entry.skill_score,
                touch_count=entry.touch_count,
                last_touch=entry.last_touch,
            )
            db.add(profile)

    await db.flush()
    return count, unmatched


async def cleanup_stale_references(
    db: AsyncSession,
    org_id: uuid.UUID,
    deleted_files: list[str],
) -> int:
    """Deactivate knowledge items whose source_ref matches a deleted file.

    Items are soft-deleted (is_active=False) so they can be recovered.

    Args:
        db: The async database session.
        org_id: Organization UUID.
        deleted_files: List of deleted file paths.

    Returns:
        Number of items deactivated.
    """
    if not deleted_files:
        return 0

    ki_repo = KnowledgeItemRepository(db, org_id=org_id)
    items = await ki_repo.list_active_items()

    deactivated = 0
    deleted_set = set(deleted_files)

    for item in items:
        if item.source_ref and item.source_ref in deleted_set:
            item.is_active = False
            # Keep embedding intact — if reactivated later it won't need
            # re-embedding (Bug 8 fix).
            deactivated += 1

    logger.info(
        "stale_cleanup",
        org_id=str(org_id),
        deleted_files=len(deleted_files),
        deactivated=deactivated,
    )
    return deactivated


async def embed_missing_items(db: AsyncSession, org_id: uuid.UUID) -> int:
    """Embed all knowledge items that are missing embeddings.

    Processes in batches of 20 to avoid overloading the embedding service.

    Args:
        db: The async database session.
        org_id: Organization UUID.

    Returns:
        Number of items embedded.
    """
    ki_repo = KnowledgeItemRepository(db, org_id=org_id)
    items = await ki_repo.list_missing_embeddings()

    if not items:
        return 0

    batch_size = 50
    total_embedded = 0

    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        texts = [f"{item.title}\n{item.content or ''}"[:2000] for item in batch]

        try:
            vectors = await embedding_service.embed_batch(texts)
            for item, vector in zip(batch, vectors, strict=True):
                item.embedding = vector
            await db.flush()
            total_embedded += len(batch)
        except Exception:
            logger.exception("embed_batch_failed", batch_start=i, batch_size=len(batch))
            # Retry one-by-one so a single bad item doesn't block the rest
            for single_item in batch:
                try:
                    text = f"{single_item.title}\n{single_item.content or ''}"[:2000]
                    single_item.embedding = await embedding_service.embed(text)
                    total_embedded += 1
                except Exception:
                    logger.warning("embed_single_failed", title=single_item.title)
            await db.flush()
            continue

    logger.info("embed_missing_items", org_id=str(org_id), embedded=total_embedded)
    return total_embedded


async def load_feature_map(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_id: uuid.UUID | None = None,
) -> FeatureMap:
    """Load (feature_name, flattened_path_list, feature_id) from active features.

    Strips the ``Feature:`` title prefix to produce clean names for skill
    profiles.  Sorts by path length descending so longest-prefix matching
    works correctly.

    When ``repo_id`` is provided, code_locations are read from the
    ``knowledge_to_repo`` junction table for that specific repo, giving
    per-repo path accuracy.

    Args:
        db: The async database session.
        org_id: Organization UUID.
        repo_id: Optional repo filter — reads per-repo code_locations
            from the junction table instead of the denormalized field.

    Returns:
        List of (feature_name, [path_prefixes], knowledge_item_id) tuples.
    """
    from app.models.knowledge_item import KnowledgeRepoLink

    ki_repo = KnowledgeItemRepository(db, org_id=org_id)
    items = await ki_repo.list_active(category="feature_registry", limit=500)

    # Build a per-repo code_locations lookup from junction table
    junction_locs: dict[uuid.UUID, dict] = {}
    if repo_id:
        rows = await db.execute(
            sa_select(KnowledgeRepoLink.knowledge_id, KnowledgeRepoLink.code_locations).where(
                KnowledgeRepoLink.repo_id == repo_id,
                KnowledgeRepoLink.code_locations.is_not(None),
            )
        )
        for kid, locs in rows.all():
            junction_locs[kid] = locs

    prefix_re = re.compile(r"^Feature:\s*")
    result: FeatureMap = []

    for item in items:
        # Read code_locations from junction table (per-repo) or merged from all links
        locs = junction_locs.get(item.id)
        if not locs:
            # No repo_id filter — merge code_locations from all junction links
            merged_locs: dict[str, list[str]] = {}
            for link in getattr(item, "repo_links", []):
                if link.code_locations:
                    merged_locs = merge_code_locations(merged_locs, link.code_locations)
            locs = merged_locs or None
        # Clean feature name
        name = prefix_re.sub("", item.title).strip()
        if not name:
            continue
        # Flatten all layer paths into one list
        all_paths: list[str] = []
        if locs:
            for paths in locs.values():
                if isinstance(paths, list):
                    all_paths.extend(paths)
        # Include features even with empty paths — they can still match
        # via directory-name fallback in _file_to_feature().
        result.append((name, all_paths, item.id))

    # Sort by longest path first for greedy matching
    result.sort(key=lambda entry: max((len(p) for p in entry[1]), default=0), reverse=True)
    return result


async def link_orphan_features(
    db: AsyncSession,
    org_id: uuid.UUID,
    ki_repo: KnowledgeItemRepository,
) -> int:
    """Auto-link orphan features (no repo link) to tracked repos.

    Matches code_location paths against tracked repository directory names.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        ki_repo: Knowledge item repository instance.

    Returns:
        Number of orphan features linked.
    """
    orphans = await ki_repo.list_active_without_repo_links("feature_registry")
    if not orphans:
        return 0

    from app.repositories.tracked_repository import TrackedRepoRepository

    tr_repo = TrackedRepoRepository(db, org_id=org_id)
    tracked_repos = await tr_repo.list_active()
    if not tracked_repos:
        return 0

    # Orphan features have no junction links (hence no code_locations).
    # Best-effort: match by single-repo org (link all orphans to the only repo).
    linked = 0
    if len(tracked_repos) == 1:
        repo = tracked_repos[0]
        for item in orphans:
            await ki_repo.link_to_repo(item.id, repo.id)
            linked += 1
    else:
        # Multi-repo: skip — orphans will be linked on next scan when
        # synthesis provides repo_name.
        logger.warning(
            "orphan_features_no_auto_link",
            count=len(orphans),
            reason="multi-repo org, no code_locations to match",
        )
    if linked:
        await db.flush()
        logger.info("orphan_features_linked", count=linked, total_orphans=len(orphans))
    return linked
