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

"""Resolve the set of users who contributed work to a BUD.

Used by the stage-promotion XP split: when a PR merges into one of a
tracked repo's release stage branches, the per-stage XP is divided
equally among everyone whose work is included in that BUD. "Contributed"
means *either* recorded a dev_activity row against the BUD *or* opened
a PR linked to the BUD. The union covers both human commits and the
agent-spawned PRs that don't always generate activity rows.

This module exists to keep the union policy out of repository code,
where each repo answers only for its own table. The two source repos
stay single-purpose; only this composer knows the union exists.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.dev_activity import DevActivityLogRepository
from app.repositories.pull_request import PullRequestRepository


async def get_bud_contributors(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
) -> set[uuid.UUID]:
    """Union of dev_activity user_ids and pull_request authors for a BUD."""
    activity_authors = await DevActivityLogRepository(
        db, org_id=org_id
    ).get_distinct_user_ids_for_bud(bud_id)
    pr_authors = await PullRequestRepository(
        db, org_id=org_id
    ).get_distinct_author_user_ids_for_bud(bud_id)
    return activity_authors | pr_authors
