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


# Only frontend → backend cross-layer verification.
# Backend-to-backend and processor pairs are handled within the cluster-merge
# stage; the pair stage is reserved for surfacing frontend↔backend twins that
# the embedding threshold missed.
ALLOWED_PAIRS: frozenset[frozenset[XLMRepoLayer]] = frozenset(
    {
        frozenset({XLMRepoLayer.FRONTEND, XLMRepoLayer.BACKEND}),
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
            # For frontend×backend pairs, guarantee repo_a is always frontend so
            # the verifier can use repo_a as the canonical anchor without
            # inspecting layer values.
            source, target = (
                (repo_a, repo_b)
                if repo_a.repo_layer == XLMRepoLayer.FRONTEND
                else (repo_b, repo_a)
            )
            assert source.repo_layer is not None
            assert target.repo_layer is not None
            rows.append(
                XLMPairPlan(
                    repo_a_id=source.id,
                    repo_b_id=target.id,
                    pair_kind=_pair_kind(source.repo_layer, target.repo_layer),
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
