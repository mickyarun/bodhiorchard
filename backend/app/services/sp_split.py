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

"""Split a fixed Skill-Point pool across weighted recipients.

This is the SP analogue of ``stage_award.award_stage_xp_to_contributors``:
a single, scarce pool divided among the people who actually did the work,
weighted by their contribution and deduped per recipient so webhook /
re-close replays never double-credit.

The division uses the *largest-remainder* method on whole cents so the
awarded shares sum back to ``pool`` exactly (no rounding drift), and no
recipient with a positive weight is silently rounded to nothing while
cents remain to distribute. Recipients whose final share is zero (only
possible when ``pool`` has fewer cents than there are recipients) are
skipped rather than recorded as zero-value audit rows.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sp_service import award_sp

logger = structlog.get_logger(__name__)


def compute_shares(pool: float, weights: dict[uuid.UUID, float]) -> dict[uuid.UUID, float]:
    """Divide ``pool`` across ``weights`` via largest-remainder on whole cents.

    Only strictly-positive weights take part (zero/negative weights — e.g. a
    todo the judge scored as trivial — are dropped). Returns a mapping of
    recipient → share (2 dp) for every recipient that ends up with > 0; the
    returned values sum to ``pool`` (to the cent) whenever at least one cent
    per recipient is available.
    """
    positive = {uid: w for uid, w in weights.items() if w > 0}
    total_weight = sum(positive.values())
    pool_cents = round(pool * 100)
    if not positive or total_weight <= 0 or pool_cents <= 0:
        return {}

    # Floor each share to whole cents, tracking the fractional remainder so
    # the leftover cents can be handed to the largest remainders.
    floor_cents: dict[uuid.UUID, int] = {}
    remainders: dict[uuid.UUID, float] = {}
    for uid, weight in positive.items():
        exact = pool_cents * weight / total_weight
        floored = int(exact)
        floor_cents[uid] = floored
        remainders[uid] = exact - floored

    leftover = pool_cents - sum(floor_cents.values())
    # Deterministic tie-break on the uuid string keeps replays stable.
    ranked = sorted(positive, key=lambda u: (-remainders[u], str(u)))
    for uid in ranked[:leftover]:
        floor_cents[uid] += 1

    return {uid: cents / 100 for uid, cents in floor_cents.items() if cents > 0}


async def award_split_sp(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    pool: float,
    weights: dict[uuid.UUID, float],
    source: str,
    ref_prefix: str,
    bud_number: int,
) -> int:
    """Award each recipient their largest-remainder share of ``pool``.

    Dedup key is ``f"{ref_prefix}:{bud_number}:{user_id}"`` so the same
    (recipient, bud, rule) triple is only ever credited once. Per-recipient
    failures are logged and swallowed — one bad award must not block the
    rest. Returns the count of recipients newly credited (post-dedup).
    """
    shares = compute_shares(pool, weights)
    if not shares:
        logger.info("sp_split_no_recipients", source=source, bud_number=bud_number)
        return 0

    awarded = 0
    for user_id, amount in shares.items():
        try:
            result = await award_sp(
                db,
                user_id=user_id,
                org_id=org_id,
                amount=amount,
                source=source,
                source_ref=f"{ref_prefix}:{bud_number}:{user_id}",
            )
            if result is not None:
                awarded += 1
        except Exception:
            logger.warning(
                "sp_split_award_failed",
                user_id=str(user_id),
                source=source,
                bud_number=bud_number,
                exc_info=True,
            )

    if awarded:
        logger.info(
            "sp_split_awarded",
            source=source,
            bud_number=bud_number,
            recipients=len(shares),
            new_awards=awarded,
        )
    return awarded
