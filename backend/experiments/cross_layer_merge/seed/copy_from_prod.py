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

"""Copy live prod rows into ``xlm_*`` tables for sandbox simulation.

Replacement for ``seed_data.json`` when you want to simulate against
the **current** production state instead of a stale fixture. Copies:

- ``tracked_repositories`` (active only) → ``xlm_tracked_repo``
- ``synthesized_features`` (latest scan per org, all rows) →
  ``xlm_synth_feature``

Merge-relation columns (``knowledge_item_id``, ``merge_outcome``,
``merged_into_id``) are deliberately reset to NULL on the sandbox
side — the runner is the sole writer of those, same as production.
``xlm_knowledge_item`` and ``xlm_ki_repo_link`` are left empty;
they're outputs of the merge, not inputs.

Idempotent: truncates xlm_* before insert. Pulls all orgs by default;
pass ``org_id`` to scope to one tenant.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.feature import Feature
from app.models.feature_to_repo import FeatureToRepo, FeatureToRepoRole
from app.models.tracked_repository import RepoStatus, TrackedRepository
from experiments.cross_layer_merge.schema import (
    XLMSynthesizedFeature,
    XLMTrackedRepo,
)
from experiments.cross_layer_merge.seed.load_seed import ensure_tables, truncate_all

log = structlog.get_logger(__name__)


async def copy_from_prod(*, org_id: uuid.UUID | None = None) -> dict[str, int]:
    """Pull active repos + their latest-scan synth rows into xlm_* tables.

    Returns counts so the CLI can confirm what landed.
    """
    await ensure_tables()
    await truncate_all()

    counts: dict[str, int] = {"tracked_repos": 0, "synthesized_features": 0}

    async with AsyncSessionLocal() as session:
        repo_query = select(TrackedRepository).where(TrackedRepository.status == RepoStatus.ACTIVE)
        if org_id is not None:
            repo_query = repo_query.where(TrackedRepository.org_id == org_id)
        repos = list((await session.execute(repo_query)).scalars().all())

        for repo in repos:
            session.add(
                XLMTrackedRepo(
                    id=repo.id,
                    org_id=repo.org_id,
                    name=repo.name,
                    path=repo.path,
                )
            )
        counts["tracked_repos"] = len(repos)
        await session.flush()

        repo_ids = {repo.id for repo in repos}
        if not repo_ids:
            await session.commit()
            log.warning("copy_from_prod.no_repos", org_id=str(org_id) if org_id else None)
            return counts

        # Pull every synth row that belongs to one of the copied repos.
        # Production keeps history via ``superseded_at``; we want the
        # current pool only — same filter prod's
        # ``list_unmerged_org_wide`` would apply except we don't filter
        # by ``merge_outcome`` because we need ALL current rows
        # (canonical, merged_into, anything) to re-run the merge from
        # scratch in the sandbox.
        # Pull each Feature row plus its PRIMARY junction so we can
        # rebuild the experiment's denormalised (repo_id, code_locations)
        # shape. The schema split moved those two fields into
        # ``feature_to_repo``; the sandbox table still keeps them inline.
        synth_query = (
            select(Feature, FeatureToRepo)
            .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
            .where(
                FeatureToRepo.repo_id.in_(repo_ids),
                FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
                Feature.superseded_at.is_(None),
            )
        )
        synth_rows = list((await session.execute(synth_query)).all())

        for synth, primary_link in synth_rows:
            session.add(
                XLMSynthesizedFeature(
                    id=synth.id,
                    scan_id=synth.scan_id,
                    org_id=synth.org_id,
                    repo_id=primary_link.repo_id,
                    feature_title=synth.feature_title,
                    description=synth.description,
                    capabilities=dict(synth.capabilities or {}),
                    cluster_names=list(synth.cluster_names or []),
                    tags=list(synth.tags or []),
                    code_locations=dict(primary_link.code_locations or {}),
                    embedding=list(synth.embedding) if synth.embedding is not None else None,
                    # Reset merge state — runner re-derives it.
                    knowledge_item_id=None,
                    merge_outcome=None,
                    merged_into_id=None,
                )
            )
        counts["synthesized_features"] = len(synth_rows)

        await session.commit()

    log.info("copy_from_prod.done", **counts)
    return counts
