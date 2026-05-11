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

"""AI bug linker: auto-detect which BUD a bug belongs to via vector similarity.

Given a bug's title + description, generates an embedding and finds the
closest BUD by cosine distance on the BUD embedding vectors. If the
distance is below the confidence threshold, auto-links the bug to that
BUD by setting ``bug.bud_id``.

Called from:
- Bug create endpoint (background task on creation)
- Slack bug intake (after extracting bug details)
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.bug import Bug
from app.repositories.bud import BUDRepository
from app.services.embedding_service import embedding_service

logger = structlog.get_logger(__name__)

# Maximum cosine distance to consider a match. Lower = stricter.
# 0.40 catches semantically related bugs (e.g. "Notification list not
# opening" matches "Notification Bell Improvement" at ~0.37 distance).
# Tunable per org in the future via org config.
AUTO_LINK_THRESHOLD = 0.40


async def embed_and_link_bug(
    db: AsyncSession,
    org_id: uuid.UUID,
    bug: Bug,
) -> BUDDocument | None:
    """Generate embedding for the bug and auto-link to the closest BUD.

    Steps:
    1. Embed ``bug.title + " " + bug.description``
    2. Query BUD embeddings via pgvector cosine distance
    3. If closest match < threshold and bug has no ``bud_id``: auto-link

    Returns the matched BUD if linked, ``None`` otherwise.
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

    # Skip auto-link if already linked manually
    if bug.bud_id:
        return None

    matched_bud = await find_closest_bud(db, org_id, vector)
    if matched_bud:
        bug.bud_id = matched_bud.id
        logger.info(
            "bug_auto_linked",
            bug_id=str(bug.id),
            bud_id=str(matched_bud.id),
            bud_number=matched_bud.bud_number,
        )
    return matched_bud


async def find_closest_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    vector: list[float],
    threshold: float = AUTO_LINK_THRESHOLD,
) -> BUDDocument | None:
    """Find the BUD whose embedding is closest to the given vector.

    Returns ``None`` if no BUD is within the threshold distance, or if
    no BUDs have embeddings at all.
    """
    pair = await BUDRepository(db, org_id=org_id).find_nearest_full_with_distance(vector)
    if pair is None:
        return None

    bud, distance = pair
    if distance > threshold:
        logger.debug(
            "bug_link_no_match",
            closest_bud=bud.bud_number,
            distance=round(distance, 4),
            threshold=threshold,
        )
        return None

    return bud
