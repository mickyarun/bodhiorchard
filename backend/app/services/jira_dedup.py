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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument

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
    stmt = (
        select(
            BUDDocument.id,
            BUDDocument.bud_number,
            BUDDocument.embedding.cosine_distance(candidate_vector).label("distance"),
        )
        .where(
            BUDDocument.org_id == org_id,
            BUDDocument.embedding.is_not(None),
        )
        .order_by("distance")
        .limit(1)
    )

    # Exclude BUDs from current import to avoid self-matching
    if exclude_bud_ids:
        stmt = stmt.where(BUDDocument.id.not_in(exclude_bud_ids))

    result = await db.execute(stmt)
    row = result.first()

    if row is None:
        return DedupResult(
            is_duplicate=False,
            needs_review=False,
            distance=None,
            matched_bud_id=None,
            matched_bud_number=None,
            note="No existing BUDs with embeddings",
        )

    bud_id, bud_number, distance = row

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
