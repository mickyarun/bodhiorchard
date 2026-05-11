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

"""Data access for the ``feature_to_repo`` junction table.

Two writers, both per-scan:

* :func:`upsert_primary` — called by ``persist_synth_feature`` after a
  feature row is inserted. Creates (or updates) the single PRIMARY row
  capturing where the feature was synthesised plus its source-side
  ``code_locations``.
* :func:`upsert_backend_links` — called by the ``backend_link`` stage on
  frontend repos with the matched backend repos and their api paths.
  Idempotent: re-running a scan replaces existing BACKEND rows.

Reads are mostly via :class:`Feature.repo_links` relationship loading,
but bulk lookups (``backend_repos_for_features``, …) live here so the
backend_link stage and downstream renderers don't have to traverse the
ORM graph.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, distinct, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature import Feature
from app.models.feature_to_repo import FeatureToRepo, FeatureToRepoRole


async def upsert_primary(
    db: AsyncSession,
    *,
    feature_id: uuid.UUID,
    repo_id: uuid.UUID,
    feature_title: str,
    code_locations: dict[str, list[str]] | None,
) -> None:
    """Insert (or refresh) the single PRIMARY row for a feature.

    Uses Postgres ``ON CONFLICT (feature_id, repo_id) DO UPDATE`` so a
    re-run of synthesis for the same feature title doesn't fail the
    unique constraint. ``code_locations`` is overwritten on conflict so
    the latest scan's file list wins.

    ``feature_title`` is denormalised from the parent ``features`` row to
    let the ``ux_ftr_primary_title`` partial unique index enforce
    one-PRIMARY-per-(repo, title) at the DB level.
    """
    stmt = (
        pg_insert(FeatureToRepo)
        .values(
            feature_id=feature_id,
            repo_id=repo_id,
            role=FeatureToRepoRole.PRIMARY,
            feature_title=feature_title,
            code_locations=code_locations,
        )
        .on_conflict_do_update(
            index_elements=["feature_id", "repo_id"],
            set_={
                "code_locations": code_locations,
                "role": FeatureToRepoRole.PRIMARY,
                "feature_title": feature_title,
            },
        )
    )
    await db.execute(stmt)


async def replace_backend_links(
    db: AsyncSession,
    *,
    feature_id: uuid.UUID,
    feature_title: str,
    backend_repos: list[tuple[uuid.UUID, list[str], dict[str, list[str]] | None]],
) -> None:
    """Replace all BACKEND junction rows for one feature.

    Deletes existing BACKEND rows for the feature, then inserts the new
    set. This keeps the row set in lockstep with the most recent
    backend-link run instead of accumulating stale matches across
    re-scans.

    Args:
        feature_id: Feature whose BACKEND links are being rewritten.
        feature_title: Denormalised onto each new BACKEND row to satisfy
            the ``feature_title NOT NULL`` column. The partial unique
            index only covers PRIMARY rows, so duplicate-title BACKEND
            rows are still legal.
        backend_repos: ``[(repo_id, [api_path, …], code_locations), …]``
            triples. ``api_paths`` MUST be non-empty — a BACKEND
            junction row without matched paths is meaningless.
            ``code_locations`` follows the same JSON shape as PRIMARY
            rows (``{"backend": [file_path, …]}``); pass ``None`` only
            in the degenerate case where the index lookup matched but
            yielded no file. Callers that want to clear all BACKEND
            rows pass an empty top-level list.
    """
    await db.execute(
        delete(FeatureToRepo).where(
            FeatureToRepo.feature_id == feature_id,
            FeatureToRepo.role == FeatureToRepoRole.BACKEND,
        )
    )
    if not backend_repos:
        return
    for repo_id, api_paths, _code_locations in backend_repos:
        if not api_paths:
            raise ValueError(
                f"replace_backend_links: empty api_paths for repo {repo_id} "
                f"(feature {feature_id}). Filter empty buckets before calling."
            )
    db.add_all(
        FeatureToRepo(
            feature_id=feature_id,
            repo_id=repo_id,
            role=FeatureToRepoRole.BACKEND,
            feature_title=feature_title,
            api_paths=api_paths,
            code_locations=code_locations,
        )
        for repo_id, api_paths, code_locations in backend_repos
    )


async def count_backend_links(
    db: AsyncSession,
    feature_id: uuid.UUID,
) -> int:
    """Existing BACKEND junction row count for one feature.

    Used by the linker's "about to clear" diagnostic — when we're about
    to write ``replace_backend_links([])`` and there are existing
    rows we'd be wiping, log a warning so a regression that
    accidentally nukes a feature's link set surfaces in ops logs
    instead of failing silently.
    """
    result = await db.execute(
        select(func.count(FeatureToRepo.id)).where(
            FeatureToRepo.feature_id == feature_id,
            FeatureToRepo.role == FeatureToRepoRole.BACKEND,
        )
    )
    return int(result.scalar_one() or 0)


async def list_for_feature(
    db: AsyncSession,
    feature_id: uuid.UUID,
) -> list[FeatureToRepo]:
    """All junction rows (PRIMARY + BACKEND) for one feature."""
    result = await db.execute(
        select(FeatureToRepo)
        .where(FeatureToRepo.feature_id == feature_id)
        .order_by(FeatureToRepo.role, FeatureToRepo.created_at)
    )
    return list(result.scalars().all())


async def outbound_link_counts(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
) -> dict[uuid.UUID, int]:
    """``{primary_repo_id: count_of_features_with_any_backend_link}``.

    Currently has no in-tree caller — the Settings → Code chip that
    used to consume it was removed (per-repo aggregate over a buggy
    per-feature write hid silent regressions). Kept available for the
    future Feature tab in the frontend, which will render per-feature
    junction rows directly. Cheap one-shot grouped query; safe to leave.
    """
    primary = FeatureToRepo.__table__.alias("primary")
    backend = FeatureToRepo.__table__.alias("backend")
    stmt = (
        select(
            primary.c.repo_id,
            func.count(distinct(primary.c.feature_id)).label("linked"),
        )
        .select_from(
            primary.join(Feature, Feature.id == primary.c.feature_id).join(
                backend, backend.c.feature_id == primary.c.feature_id
            )
        )
        .where(
            Feature.org_id == org_id,
            primary.c.role == FeatureToRepoRole.PRIMARY,
            backend.c.role == FeatureToRepoRole.BACKEND,
        )
        .group_by(primary.c.repo_id)
    )
    result = await db.execute(stmt)
    return {row.repo_id: int(row.linked) for row in result.all()}


async def list_backend_links_grouped(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    feature_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[FeatureToRepo]]:
    """``{feature_id: [backend_link, …]}`` for a batch of features.

    The Features-tab API loads features in pages, then needs every
    BACKEND junction row for each so the inline expand panel can
    render "depends on backend". Doing one IN-list query per page
    avoids the N+1 selectin pattern.
    """
    if not feature_ids:
        return {}
    result = await db.execute(
        select(FeatureToRepo)
        .join(Feature, Feature.id == FeatureToRepo.feature_id)
        .where(
            Feature.org_id == org_id,
            FeatureToRepo.feature_id.in_(feature_ids),
            FeatureToRepo.role == FeatureToRepoRole.BACKEND,
        )
        .order_by(FeatureToRepo.feature_id, FeatureToRepo.created_at)
    )
    grouped: dict[uuid.UUID, list[FeatureToRepo]] = {}
    for row in result.scalars().all():
        grouped.setdefault(row.feature_id, []).append(row)
    return grouped


async def inbound_link_counts(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
) -> dict[uuid.UUID, int]:
    """``{backend_repo_id: count_of_distinct_frontend_features_linking_in}``.

    Counterpart to :func:`outbound_link_counts`. Same status — kept
    for the future Feature tab; not consumed by Settings → Code today.
    """
    stmt = (
        select(
            FeatureToRepo.repo_id,
            func.count(distinct(FeatureToRepo.feature_id)).label("inbound"),
        )
        .select_from(FeatureToRepo.__table__.join(Feature, Feature.id == FeatureToRepo.feature_id))
        .where(
            Feature.org_id == org_id,
            FeatureToRepo.role == FeatureToRepoRole.BACKEND,
        )
        .group_by(FeatureToRepo.repo_id)
    )
    result = await db.execute(stmt)
    return {row.repo_id: int(row.inbound) for row in result.all()}
