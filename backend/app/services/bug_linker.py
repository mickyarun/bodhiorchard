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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.bug import Bug
from app.services.embedding_service import embedding_service

logger = structlog.get_logger(__name__)

# Maximum cosine distance to consider a match. Lower = stricter.
# 0.35 is a good balance: catches semantically related bugs without
# false-linking unrelated ones. Tunable per org in the future.
AUTO_LINK_THRESHOLD = 0.35


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
    stmt = (
        select(
            BUDDocument,
            BUDDocument.embedding.cosine_distance(vector).label("distance"),
        )
        .where(
            BUDDocument.org_id == org_id,
            BUDDocument.embedding.is_not(None),
        )
        .order_by("distance")
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        return None

    bud, distance = row
    if distance > threshold:
        logger.debug(
            "bug_link_no_match",
            closest_bud=bud.bud_number,
            distance=round(distance, 4),
            threshold=threshold,
        )
        return None

    return bud
