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

"""AI bug linker — auto-detect the closest BUD or Feature for a bug.

Two surfaces, one entry point. The bug's ``bug_type`` decides which
embedding pool the linker matches against:

- ``bug_type == PRODUCTION`` (and no manual ``feature_id``) → match
  against shipped :class:`app.models.feature.Feature` embeddings via
  :meth:`FeatureReadRepository.semantic_search`. This is the /bugs
  Kanban path: the user reports a prod bug and the AI links it to the
  Feature it most likely belongs to.
- otherwise (and no manual ``bud_id``) → match against
  :class:`app.models.bud.BUDDocument` embeddings. This is the legacy
  BUDBugsPanel + Slack-intake path for testing bugs.

When the Feature path matches and the bug had no ``bud_id``, the linker
also stamps ``bug_type = PRODUCTION`` — that's the source of truth for
SP attribution and board placement downstream.

Callers:

- Bug create endpoint (``app/api/v1/bugs.py``) — inline, awaited so the
  response includes the resolved link.
- Slack bug intake (``app/services/slack_bug_intake.py``) — testing-bug
  surface; only ever hits the BUD path because ``bug_type`` defaults to
  ``testing``.
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.bug import Bug, BugType
from app.models.feature import Feature
from app.repositories.bud import BUDRepository
from app.repositories.feature_reads import FeatureReadRepository
from app.services.embedding_service import embedding_service

logger = structlog.get_logger(__name__)

# Maximum cosine distance to consider a match. Lower = stricter.
# 0.40 catches semantically related bugs (e.g. "Notification list not
# opening" matches "Notification Bell Improvement" at ~0.37 distance).
# Tunable per org in the future via org config.
AUTO_LINK_THRESHOLD = 0.40
# Feature embeddings are computed from ``feature_title + description``
# of a synthesised cluster — broader / noisier than a BUD's single
# requirement statement. Use a stricter threshold to keep false-positive
# auto-links manageable. Tune by watching false-link rate per org.
# TODO: per-org tuning via org config (mirror the AUTO_LINK_THRESHOLD plan).
AUTO_LINK_FEATURE_THRESHOLD = 0.35


async def embed_and_link_bug(
    db: AsyncSession,
    org_id: uuid.UUID,
    bug: Bug,
) -> BUDDocument | Feature | None:
    """Generate the bug's embedding and auto-link to the closest BUD or Feature.

    Steps:

    1. Embed ``bug.title + " " + bug.description``.
    2. Decide which pool to match against (see module docstring).
    3. If the closest match is within the per-pool threshold and the
       bug has no manual link of that kind, set the FK on the ORM
       instance (caller is responsible for ``flush`` / ``refresh``).

    Returns the matched ORM instance, or ``None`` when nothing
    qualifies. Callers that only handle one kind of match should
    narrow the return type with ``isinstance`` — the slack intake
    path does this because it only ever speaks the BUD shape.
    """
    text = bug.title
    if bug.description:
        text = f"{text} {bug.description}"

    try:
        vector = await embedding_service.embed(text)
    except Exception:
        logger.warning("bug_embedding_failed", bug_id=str(bug.id), exc_info=True)
        return None

    bug.embedding = vector

    if bug.bug_type == BugType.PRODUCTION and bug.feature_id is None:
        feature = await _link_to_feature(db, org_id, bug, vector)
        # No BUD fallback by design: a production bug whose closest Feature
        # is past threshold stays unlinked. Falling back to BUD matching
        # would mis-attribute prod bugs to in-flight BUDs and confuse the
        # SP penalty path.
        return feature

    if bug.bud_id is None:
        return await _link_to_bud(db, org_id, bug, vector)

    return None


async def _link_to_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    bug: Bug,
    vector: list[float],
) -> BUDDocument | None:
    """Attach ``bug.bud_id`` to the closest BUD within threshold."""
    matched = await find_closest_bud(db, org_id, vector)
    if matched is None:
        return None
    bug.bud_id = matched.id
    logger.info(
        "bug_auto_linked_bud",
        bug_id=str(bug.id),
        bud_id=str(matched.id),
        bud_number=matched.bud_number,
    )
    return matched


async def _link_to_feature(
    db: AsyncSession,
    org_id: uuid.UUID,
    bug: Bug,
    vector: list[float],
) -> Feature | None:
    """Attach ``bug.feature_id`` to the closest active Feature within threshold.

    Also stamps ``bug.bug_type = PRODUCTION`` so the board placement and
    SP attribution downstream see the correct kind. The caller is
    responsible for flushing.
    """
    matched = await find_closest_feature(db, org_id, vector)
    if matched is None:
        return None
    bug.feature_id = matched.id
    bug.bug_type = BugType.PRODUCTION
    logger.info(
        "bug_auto_linked_feature",
        bug_id=str(bug.id),
        feature_id=str(matched.id),
        feature_title=matched.feature_title,
    )
    return matched


async def find_closest_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    vector: list[float],
    threshold: float = AUTO_LINK_THRESHOLD,
) -> BUDDocument | None:
    """Find the BUD whose embedding is closest to the given vector.

    Returns ``None`` if no BUD is within the threshold distance, or if
    no BUDs in the org have embeddings at all.
    """
    pair = await BUDRepository(db, org_id=org_id).find_nearest_full_with_distance(vector)
    if pair is None:
        return None

    bud, distance = pair
    if distance > threshold:
        logger.debug(
            "bug_link_no_match_bud",
            closest_bud=bud.bud_number,
            distance=round(distance, 4),
            threshold=threshold,
        )
        return None

    return bud


async def find_closest_feature(
    db: AsyncSession,
    org_id: uuid.UUID,
    vector: list[float],
    threshold: float = AUTO_LINK_FEATURE_THRESHOLD,
) -> Feature | None:
    """Find the active Feature whose embedding is closest to the vector.

    Reuses :meth:`FeatureReadRepository.semantic_search` with
    ``limit=1`` so the hnsw index does the heavy lifting. Soft-deleted
    Features (``is_active=False``) are excluded — bug links against
    deactivated features would mislead the SP attribution.
    """
    pool = FeatureReadRepository(db, org_id=org_id)
    matches = await pool.semantic_search(vector, limit=1, only_active=True)
    if not matches:
        return None

    feature, distance = matches[0]
    if distance > threshold:
        logger.debug(
            "bug_link_no_match_feature",
            closest_feature=feature.feature_title,
            distance=round(distance, 4),
            threshold=threshold,
        )
        return None

    return feature
