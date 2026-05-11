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

"""Semantic deduplication for Jira import (Layer 2).

Checks candidate BUDs against existing BUDs in the org using pgvector
cosine distance. Classifies results by threshold:

- distance < 0.25 → DUPLICATE_CANDIDATE (auto-skip)
- 0.25 ≤ distance < 0.40 → REVIEW_NEEDED (flag for user)
- distance ≥ 0.40 → unique (create new BUD)

Reuses the same embedding model (BAAI/bge-small-en-v1.5, 384d) and
pgvector query pattern as ``bug_linker.py``.
"""

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.bud import BUDRepository

logger = structlog.get_logger(__name__)

# Thresholds calibrated from bug_linker.py (0.40) and tightened
# for BUD-to-BUD matching where we expect higher similarity for true dupes.
THRESHOLD_AUTO_SKIP = 0.25
THRESHOLD_REVIEW = 0.40


@dataclass
class DedupResult:
    """Result of a semantic dedup check for one candidate."""

    is_duplicate: bool
    needs_review: bool
    distance: float | None
    matched_bud_id: uuid.UUID | None
    matched_bud_number: int | None
    note: str


async def check_semantic_duplicate(
    db: AsyncSession,
    org_id: uuid.UUID,
    candidate_vector: list[float],
    *,
    exclude_bud_ids: set[uuid.UUID] | None = None,
) -> DedupResult:
    """Check if a candidate embedding is semantically similar to any existing BUD.

    Args:
        db: Async database session.
        org_id: Organization scope.
        candidate_vector: 384-dim embedding vector for the candidate.
        exclude_bud_ids: BUDs created during this import session to skip
            (prevents matching against just-imported BUDs).

    Returns:
        DedupResult with classification and matched BUD info.
    """
    nearest = await BUDRepository(db, org_id=org_id).find_nearest_neighbor(
        candidate_vector,
        exclude_bud_ids=list(exclude_bud_ids) if exclude_bud_ids else None,
    )
    if nearest is None:
        return DedupResult(
            is_duplicate=False,
            needs_review=False,
            distance=None,
            matched_bud_id=None,
            matched_bud_number=None,
            note="No existing BUDs with embeddings",
        )

    bud_id, bud_number, distance = nearest

    if distance < THRESHOLD_AUTO_SKIP:
        return DedupResult(
            is_duplicate=True,
            needs_review=False,
            distance=round(distance, 4),
            matched_bud_id=bud_id,
            matched_bud_number=bud_number,
            note=f"Very similar to BUD-{bud_number} (distance={distance:.3f})",
        )

    if distance < THRESHOLD_REVIEW:
        return DedupResult(
            is_duplicate=False,
            needs_review=True,
            distance=round(distance, 4),
            matched_bud_id=bud_id,
            matched_bud_number=bud_number,
            note=f"May overlap with BUD-{bud_number} (distance={distance:.3f})",
        )

    return DedupResult(
        is_duplicate=False,
        needs_review=False,
        distance=round(distance, 4),
        matched_bud_id=None,
        matched_bud_number=None,
        note="Sufficiently unique",
    )
