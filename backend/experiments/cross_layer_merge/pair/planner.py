# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Plan which repo pairs the verifier will compare for cross-layer merges.

Emits one ``XLMPairPlan`` row per unordered pair of repos whose
classifications cross a layer boundary we care about. The output is
deterministic (sorted by name) so pair IDs are stable across reloads
during prompt-iteration cycles.
"""

from itertools import combinations

import structlog
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from experiments.cross_layer_merge.schema import (
    XLMPairPlan,
    XLMPairStatus,
    XLMRepoLayer,
    XLMTrackedRepo,
)

log = structlog.get_logger(__name__)


# Pairs we WILL evaluate. Frozensets so order doesn't matter on lookup.
ALLOWED_PAIRS: frozenset[frozenset[XLMRepoLayer]] = frozenset(
    {
        frozenset({XLMRepoLayer.FRONTEND, XLMRepoLayer.BACKEND}),
        frozenset({XLMRepoLayer.FRONTEND, XLMRepoLayer.PROCESSOR}),
        frozenset({XLMRepoLayer.BACKEND, XLMRepoLayer.PROCESSOR}),
        # Microservices share features internally.
        frozenset({XLMRepoLayer.BACKEND}),
    }
)


def _pair_kind(a: XLMRepoLayer, b: XLMRepoLayer) -> str:
    """Stable label for a pair regardless of arg order."""
    return "×".join(sorted([a.value, b.value]))


def _is_allowed(a: XLMRepoLayer, b: XLMRepoLayer) -> bool:
    """Same-layer pairs are allowed only if the layer's singleton set is in ALLOWED_PAIRS."""
    if a == b:
        return frozenset({a}) in ALLOWED_PAIRS
    return frozenset({a, b}) in ALLOWED_PAIRS


async def plan_pairs() -> int:
    """Read classified repos, emit pair plan, return pair count.

    Truncates ``xlm_pair_plan`` first so re-running starts fresh —
    same idempotency promise as the seed loader.
    """
    async with AsyncSessionLocal() as session:
        await session.execute(delete(XLMPairPlan))

        repos = (
            (await session.execute(select(XLMTrackedRepo).order_by(XLMTrackedRepo.name)))
            .scalars()
            .all()
        )
        classified = [r for r in repos if r.repo_layer is not None]
        if len(classified) < 2:
            log.warning("planner.too_few_classified", count=len(classified))
            return 0

        rows: list[XLMPairPlan] = []
        for repo_a, repo_b in combinations(classified, 2):
            # ``classified`` filtered out None layers above; assertions narrow types for mypy.
            assert repo_a.repo_layer is not None
            assert repo_b.repo_layer is not None
            if not _is_allowed(repo_a.repo_layer, repo_b.repo_layer):
                continue
            rows.append(
                XLMPairPlan(
                    repo_a_id=repo_a.id,
                    repo_b_id=repo_b.id,
                    pair_kind=_pair_kind(repo_a.repo_layer, repo_b.repo_layer),
                    status=XLMPairStatus.PENDING,
                )
            )

        session.add_all(rows)
        await session.commit()

    log.info("planner.emitted", pair_count=len(rows))
    return len(rows)


async def list_pending_pairs() -> list[XLMPairPlan]:
    """Return PENDING pairs in deterministic order for the verifier."""
    async with AsyncSessionLocal() as session:
        rows = (
            (
                await session.execute(
                    select(XLMPairPlan)
                    .where(XLMPairPlan.status == XLMPairStatus.PENDING)
                    .order_by(XLMPairPlan.pair_kind, XLMPairPlan.id)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)
