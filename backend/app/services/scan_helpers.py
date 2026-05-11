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

"""Reusable helpers for the scan pipeline.

Contains timing utilities, the skill-profile upsert loop (used by both
Phase E and Phase E2), and helper functions extracted from the pipeline.

Stale-cleanup, embed-missing, and orphan-link helpers were dropped
along with the legacy ``knowledge_items`` table — the reconciler
now owns soft-delete (via ``is_active`` flips) and the synth writer
embeds at insert time, so those side channels are no longer needed.
"""

import re
import time
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill_profile import SkillProfile
from app.models.user import User
from app.repositories.feature_reads import FeatureReadRepository
from app.repositories.skill_profile import SkillProfileRepository
from app.services.git_analyzer import DevSkillEntry, FeatureMap

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


async def load_feature_map(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_id: uuid.UUID | None = None,
) -> FeatureMap:
    """Load ``(feature_name, [path_prefixes], feature_id)`` triples.

    Strips the ``Feature:`` title prefix to produce clean names for
    skill profiles. Sorts by path length descending so longest-prefix
    matching works correctly. When ``repo_id`` is provided, only that
    repo's PRIMARY junction code_locations are read; otherwise every
    active feature in the org is included (BUD-authored features
    have no PRIMARY junction so their path list is empty — they
    still appear, since directory-name fallback can match them).
    """
    reads = FeatureReadRepository(db, org_id=org_id)
    if repo_id is not None:
        triples = await reads.feature_paths_for_repo(repo_id)
        prefix_re = re.compile(r"^Feature:\s*")
        result: FeatureMap = [
            (prefix_re.sub("", title).strip(), paths, fid)
            for (title, paths, fid) in triples
            if prefix_re.sub("", title).strip()
        ]
    else:
        rows = await reads.list_features_with_repo_paths()
        prefix_re = re.compile(r"^Feature:\s*")
        # ``list_features_with_repo_paths`` emits one row per PRIMARY
        # junction (or one row with repo_path=None for unbound).
        # Group by feature_id and merge code_locations across rows.
        merged: dict[uuid.UUID, tuple[str, list[str]]] = {}
        for fid, title, _src_ref, _status, code_locs, _repo_path in rows:
            name = prefix_re.sub("", title or "").strip()
            if not name:
                continue
            paths: list[str] = []
            if code_locs:
                for value in code_locs.values():
                    if isinstance(value, list):
                        paths.extend(p for p in value if isinstance(p, str))
            existing = merged.get(fid)
            if existing is None:
                merged[fid] = (name, paths)
            else:
                merged[fid] = (existing[0], existing[1] + paths)
        result = [(name, paths, fid) for fid, (name, paths) in merged.items()]
    # Sort by longest path first for greedy matching.
    result.sort(key=lambda entry: max((len(p) for p in entry[1]), default=0), reverse=True)
    return result
