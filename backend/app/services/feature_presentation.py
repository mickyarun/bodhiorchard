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

"""Read-side composition helpers for the Features-tab API.

Lives between the API handlers (``api/v1/features.py``) and the
repositories. Each helper composes one or more repository queries to
produce derived data the API needs to serialise — keeping the
handlers thin and the repos focused on single-table reads.

Today this module hosts the merge-SHA → PR-meta resolver used by the
deactivated-features filter AND the "created by / last touched by"
lineage row on every card. Future presentation-only helpers (e.g.
feature health badges, display tag derivations) belong here too.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature import Feature
from app.repositories.pull_request import PullRequestRepository


async def resolve_pr_meta_for_features(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    features: list[Feature],
) -> dict[str, tuple[int, str | None]]:
    """One bulk lookup mapping merge SHAs → ``(pr_number, html_url)``.

    Collects every distinct SHA on the page from three columns —
    ``created_at_sha``, ``last_seen_sha``, ``deactivated_at_sha`` —
    and resolves them in a single round trip. Returns a dict the
    caller indexes per-feature without further DB work.

    The deactivation field used to be the only SHA we resolved; with
    the lineage row showing "Created by PR #N · Last touched by PR #M",
    the SHA set per page grew but the dedup keeps the query small —
    in practice two contiguous merges produce ~3-5 distinct SHAs even
    across 24 features on a page.

    Returns an empty dict on an empty page or when no feature has any
    resolvable SHA, short-circuiting the round trip.
    """
    shas: set[str] = set()
    for f in features:
        if f.created_at_sha:
            shas.add(f.created_at_sha)
        if f.last_seen_sha:
            shas.add(f.last_seen_sha)
        if f.deactivated_at_sha:
            shas.add(f.deactivated_at_sha)
    if not shas:
        return {}
    # Sorted for deterministic test assertions; the bulk lookup itself
    # doesn't care about order.
    return await PullRequestRepository(db, org_id=org_id).map_shas_to_pr_meta(sorted(shas))
