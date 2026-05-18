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

"""Feature data access repository — writes + simple identity reads.

Heavier reads (paginated lists with eager-loaded junction rows,
semantic search, group-by-repo aggregates) live in
``app.repositories.feature_reads`` so this file stays focused on the
incremental-CRUD writers the reconciler depends on.

Writes happen via two paths:

* ``FEATURE_SYNTHESIS`` (MCP ``write_feature_registry``) — calls
  :meth:`insert` once per synthesised cluster, then the reconciler
  decides update-vs-insert based on ``cluster_signature`` matching.
* ``feature_reconciler`` — calls :meth:`update_in_place`,
  :meth:`revive`, and :meth:`mark_inactive` to apply the diff between
  the synthesised set and the existing active rows.

Reactivation preserves the row's ``id`` so bug links and BUD
references stay attached across remove/restore cycles.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature import Feature
from app.models.feature_to_repo import FeatureToRepo, FeatureToRepoRole
from app.repositories.base import BaseRepository


def _code_locations_overlap(
    code_locations: dict[str, Any] | None,
    affected_files: set[str],
) -> bool:
    """Return ``True`` iff any file in ``code_locations`` is in ``affected_files``.

    ``code_locations`` is JSONB shaped like ``{"frontend": [...],
    "backend": [...]}`` but the schema isn't strictly enforced — some
    rows have ``None`` values, some have non-list values. The predicate
    mirrors the reconciler's ``candidate_filter`` so the two layers
    agree on what "feature touched by these files" means.
    """
    if not code_locations:
        return False
    feat_files: set[str] = set()
    for value in code_locations.values():
        if isinstance(value, list):
            feat_files.update(p for p in value if isinstance(p, str))
    return bool(feat_files & affected_files)


class FeatureRepository(BaseRepository[Feature]):
    """Repository for ``features`` rows, org-scoped.

    Organisation scoping is inherited from ``BaseRepository``; every
    read method applies ``org_id`` via ``_scoped``. Reads that key on a
    repo (``list_current_for_repo``, ``cluster_names_for_repo``,
    ``list_primary_pairs_for_repo``) JOIN through ``feature_to_repo``
    filtering on ``role='primary'`` so they target the synthesis source
    repo, not the linked backend repos. ``count_active_per_repo``
    aggregates the same join across the whole org.
    """

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        super().__init__(Feature, db, org_id=org_id)

    async def count_active_for_org(self) -> int:
        """Total active feature count across the org (scan + BUD).

        Includes BUD-authored rows (no PRIMARY junction) so the
        dashboard "total features" metric reflects every row a user
        could meaningfully see in the Features tab plus any planned
        BUD work that hasn't been scanned yet.
        """
        stmt = self._scoped(select(func.count(Feature.id)).where(Feature.is_active.is_(True)))
        return int((await self._db.execute(stmt)).scalar_one() or 0)

    async def count_active_for_repo(self, repo_id: uuid.UUID) -> int:
        """Active feature count for one repo's PRIMARY junction.

        ``is_active=True`` filtered so soft-deleted rows do not count.
        """
        stmt = self._scoped(
            select(func.count(Feature.id))
            .select_from(Feature)
            .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
            .where(
                Feature.is_active.is_(True),
                FeatureToRepo.repo_id == repo_id,
                FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
            )
        )
        return int((await self._db.execute(stmt)).scalar_one() or 0)

    async def count_active_per_repo(self) -> dict[uuid.UUID, int]:
        """Per-repo active feature counts for the org.

        Joins through ``feature_to_repo`` on ``role='primary'`` so a
        feature is counted against the repo where it was synthesised,
        not the backend repos it links to via ``role='backend'`` rows.
        Filters ``Feature.is_active`` so the count matches what the
        Features tab renders.
        """
        stmt = self._scoped(
            select(
                FeatureToRepo.repo_id,
                func.count(Feature.id).label("synth_count"),
            )
            .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
            .where(
                Feature.is_active.is_(True),
                FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
            )
            .group_by(FeatureToRepo.repo_id)
        )
        result = await self._db.execute(stmt)
        return {row.repo_id: row.synth_count for row in result.all()}

    async def insert(
        self,
        *,
        feature_title: str,
        description: str,
        capabilities: dict[str, Any],
        cluster_names: list[str],
        cluster_signature: str,
        tags: list[str] | None = None,
        embedding: list[float] | None = None,
        source: str | None = None,
        source_ref: str | None = None,
        feature_status: str | None = None,
        last_seen_sha: str | None = None,
        created_at_sha: str | None = None,
    ) -> Feature:
        """Insert one feature row.

        Repo binding lives on ``feature_to_repo``: the synth writer
        wrapper in :mod:`app.mcp.synth_feature_writer` does the feature
        insert + the PRIMARY junction insert in the same transaction.
        BACKEND junctions land later via :func:`replace_backend_links`.

        ``cluster_signature`` is required (NOT NULL on the column) — it
        is the reconciler's primary identity key and must be present
        before the row participates in any reconcile pass.

        ``created_at_sha`` (the head_sha the reconciler was processing
        at insert time) is optional for backwards compatibility — the
        BUD lifecycle writer doesn't have one. The reconciler always
        passes it so newly-scan-authored features carry their birth
        SHA forward.
        """
        assert self._org_id is not None, "org_id required for writes"
        row = Feature(
            org_id=self._org_id,
            feature_title=feature_title,
            description=description,
            capabilities=capabilities,
            cluster_names=cluster_names,
            cluster_signature=cluster_signature,
            tags=list(tags or []),
            embedding=embedding,
            source=source,
            source_ref=source_ref,
            feature_status=feature_status,
            last_seen_sha=last_seen_sha,
            created_at_sha=created_at_sha,
            synthesized_at=datetime.now(UTC),
        )
        self._db.add(row)
        await self._db.flush()
        await self._db.refresh(row)
        return row

    async def update_in_place(
        self,
        feature_id: uuid.UUID,
        *,
        feature_title: str,
        description: str,
        capabilities: dict[str, Any],
        cluster_names: list[str],
        cluster_signature: str,
        tags: list[str],
        embedding: list[float] | None,
        last_seen_sha: str | None,
        feature_status: str | None = None,
    ) -> None:
        """Update a feature in place without changing its ``id``.

        Called by the reconciler when a synthesised feature matches an
        existing row (signature → Jaccard → cosine fallback). The
        primary key is preserved so junction rows, bug links, and BUD
        references stay attached.

        ``embedding=None`` is treated as "no fresh vector this run"
        (embedding service blip, dry run, etc.) and the existing
        column value is preserved. Callers that genuinely want to
        clear the embedding should call :meth:`set_embedding` with
        an empty vector explicitly.
        """
        values: dict[str, Any] = {
            "feature_title": feature_title,
            "description": description,
            "capabilities": capabilities,
            "cluster_names": cluster_names,
            "cluster_signature": cluster_signature,
            "tags": tags,
            "last_seen_sha": last_seen_sha,
        }
        if embedding is not None:
            values["embedding"] = embedding
        if feature_status is not None:
            values["feature_status"] = feature_status
        await self._db.execute(
            sql_update(Feature)
            .where(Feature.org_id == self._org_id, Feature.id == feature_id)
            .values(**values)
        )

    async def revive(
        self,
        feature_id: uuid.UUID,
        *,
        last_seen_sha: str | None,
    ) -> None:
        """Flip a soft-deleted row back to active.

        Clears both ``deactivated_at`` and ``deactivated_at_sha`` so the
        revived row reads as if it had never been deactivated; stamps
        ``last_seen_sha``. Field updates from the new synthesis go
        through :meth:`update_in_place` separately so a revival is
        always paired with fresh content.
        """
        await self._db.execute(
            sql_update(Feature)
            .where(Feature.org_id == self._org_id, Feature.id == feature_id)
            .values(
                is_active=True,
                deactivated_at=None,
                deactivated_at_sha=None,
                last_seen_sha=last_seen_sha,
            )
        )

    async def mark_inactive(
        self,
        feature_ids: list[uuid.UUID],
        *,
        head_sha: str | None = None,
    ) -> int:
        """Bulk soft-delete: ``is_active=False`` + stamp ``deactivated_at``.

        When ``head_sha`` is supplied (reconciler / PR-merge path), it is
        recorded in ``deactivated_at_sha`` so the deactivating commit is
        attributable in the UI. Left NULL for callers without a commit
        context (e.g. BUD discarded).

        BACKEND junctions on each feature stay intact (reads filter
        by parent ``is_active`` so they're invisible until a revive).

        Returns the number of rows touched.
        """
        if not feature_ids:
            return 0
        result = await self._db.execute(
            sql_update(Feature)
            .where(
                Feature.org_id == self._org_id,
                Feature.id.in_(feature_ids),
                Feature.is_active.is_(True),
            )
            .values(
                is_active=False,
                deactivated_at=datetime.now(UTC),
                deactivated_at_sha=head_sha,
            )
        )
        rowcount = getattr(result, "rowcount", 0) or 0
        return max(int(rowcount), 0)

    async def list_active_ids_by_signatures(
        self,
        repo_id: uuid.UUID,
        signatures: set[str],
        *,
        affected_files: set[str] | None = None,
    ) -> list[uuid.UUID]:
        """Active feature ids matching by ``cluster_signature`` OR file overlap.

        Used by the narrow PR-merge backend-link refresh to scope its
        work to the features just touched by the reconciler. Inactive
        rows are excluded — a soft-deleted feature has no cross-layer
        link to refresh.

        When ``affected_files`` is provided, the lookup widens to also
        admit features whose PRIMARY junction's ``code_locations``
        intersects that file set. This mirrors the file-overlap
        fallback :func:`_reconcile_narrow`'s ``candidate_filter`` uses,
        and closes the gap where a feature's stored
        ``cluster_signature`` drifts from the current indexer output
        across releases: the reconciler updates the feature via
        file-overlap, but the cross-layer refresh used to miss it
        because its lookup was signature-only.

        The signature path stays in SQL (cheap index hit). The
        file-overlap path loads candidate rows + their JSONB
        ``code_locations`` and filters in Python — ``code_locations``
        is heterogeneous JSONB (per-role arrays, sometimes null) and
        the in-Python predicate matches the reconciler's exactly,
        avoiding ``jsonb_typeof`` gymnastics for what's a sub-ms
        filter on a bounded feature count.
        """
        if not signatures and not affected_files:
            return []

        matched: set[uuid.UUID] = set()
        if signatures:
            sig_result = await self._db.execute(
                self._scoped(
                    select(Feature.id)
                    .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
                    .where(
                        Feature.is_active.is_(True),
                        Feature.cluster_signature.in_(signatures),
                        FeatureToRepo.repo_id == repo_id,
                        FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
                    )
                )
            )
            matched.update(row[0] for row in sig_result.all())

        if affected_files:
            file_result = await self._db.execute(
                self._scoped(
                    select(Feature.id, FeatureToRepo.code_locations)
                    .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
                    .where(
                        Feature.is_active.is_(True),
                        FeatureToRepo.repo_id == repo_id,
                        FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
                    )
                )
            )
            for fid, code_locations in file_result.all():
                if fid in matched:
                    continue
                if _code_locations_overlap(code_locations, affected_files):
                    matched.add(fid)

        return list(matched)

    async def find_by_signature(
        self,
        repo_id: uuid.UUID,
        cluster_signature: str,
    ) -> Feature | None:
        """Reconciler step-1 lookup: exact signature match within a repo.

        Scoped via the PRIMARY junction so a feature with the same
        signature in a different repo does not match. Returns the row
        regardless of ``is_active`` so soft-deleted features can be
        revived in the same call site.
        """
        result = await self._db.execute(
            self._scoped(
                select(Feature)
                .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
                .where(
                    Feature.cluster_signature == cluster_signature,
                    FeatureToRepo.repo_id == repo_id,
                    FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
                )
            )
        )
        return result.scalars().first()

    async def set_embedding(
        self,
        feature_id: uuid.UUID,
        embedding: list[float],
    ) -> None:
        """Lazy-fill ``embedding`` on a row that pre-dates the column."""
        await self._db.execute(
            sql_update(Feature)
            .where(
                Feature.org_id == self._org_id,
                Feature.id == feature_id,
            )
            .values(embedding=embedding)
        )

    async def list_active_grouped_by_repos(
        self, repo_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[Feature]]:
        """Active features for ``repo_ids`` keyed by their PRIMARY repo id.

        Filters ``Feature.is_active`` so soft-deleted rows do not leak
        into the serialise stage. Sorted by title within each repo for
        stable output.
        """
        if not repo_ids:
            return {}
        result = await self._db.execute(
            self._scoped(
                select(Feature, FeatureToRepo.repo_id)
                .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
                .where(
                    Feature.is_active.is_(True),
                    FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
                    FeatureToRepo.repo_id.in_(repo_ids),
                )
            ).order_by(FeatureToRepo.repo_id, Feature.feature_title)
        )
        grouped: dict[uuid.UUID, list[Feature]] = {}
        for feature, repo_id in result.all():
            grouped.setdefault(repo_id, []).append(feature)
        return grouped

    async def get_by_id(self, feature_id: uuid.UUID) -> Feature | None:
        """Fetch a single row by primary key within org scope."""
        result = await self._db.execute(
            self._scoped(select(Feature).where(Feature.id == feature_id))
        )
        return result.scalar_one_or_none()

    async def get_by_source_ref(
        self, source_ref: str, *, source: str | None = None
    ) -> Feature | None:
        """Look up a feature by its provenance reference (e.g. ``BUD-042``).

        Used by the BUD-authored lifecycle path to upsert by source_ref.
        Pair with ``source='bud'`` to disambiguate against scan-authored
        rows that may share a numeric reference by accident.
        """
        stmt = select(Feature).where(
            Feature.org_id == self._org_id,
            Feature.source_ref == source_ref,
        )
        if source is not None:
            stmt = stmt.where(Feature.source == source)
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def find_orphan_active_feature_ids(self) -> list[uuid.UUID]:
        """Active scan-sourced features missing their PRIMARY junction.

        Data-integrity invariant under incremental CRUD: every active
        ``source='scan'`` feature MUST have exactly one PRIMARY
        ``feature_to_repo`` row — that's where the source repo
        binding + ``code_locations`` live. BUD-authored
        (``source='bud'``) features are intentionally repo-agnostic
        and excluded from the check. The reconciler maintains the
        invariant on every pass; this audit surfaces drift introduced
        by a crashed reconcile or a race.
        """
        primary_id_subq = (
            select(FeatureToRepo.feature_id)
            .where(FeatureToRepo.role == FeatureToRepoRole.PRIMARY)
            .scalar_subquery()
        )
        result = await self._db.execute(
            self._scoped(
                select(Feature.id).where(
                    Feature.is_active.is_(True),
                    Feature.source == "scan",
                    Feature.id.not_in(primary_id_subq),
                )
            )
        )
        return [row[0] for row in result.all()]

    async def find_duplicate_signatures(
        self, repo_id: uuid.UUID
    ) -> list[tuple[str, list[uuid.UUID]]]:
        """Active features sharing a ``cluster_signature`` within one repo.

        Data-integrity invariant under incremental CRUD: each
        ``cluster_signature`` should resolve to at most one active
        feature per repo (the reconciler matches signature-first and
        UPDATEs in place). Two active rows on the same signature
        indicate drift — usually a crashed reconcile that inserted a
        new row before inactivating the old one.

        Returns ``(signature, [feature_id, ...])`` pairs for every
        signature with more than one active feature whose PRIMARY
        junction points at ``repo_id``. Empty list = healthy.
        """
        primary_subq = (
            select(FeatureToRepo.feature_id)
            .where(
                FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
                FeatureToRepo.repo_id == repo_id,
            )
            .scalar_subquery()
        )
        stmt = (
            select(
                Feature.cluster_signature,
                func.array_agg(Feature.id).label("ids"),
            )
            .where(
                Feature.org_id == self._org_id,
                Feature.is_active.is_(True),
                Feature.id.in_(primary_subq),
            )
            .group_by(Feature.cluster_signature)
            .having(func.count(Feature.id) > 1)
        )
        result = await self._db.execute(stmt)
        return [(row[0], list(row[1])) for row in result.all()]

    async def find_duplicate_signatures_for_org(
        self,
    ) -> list[tuple[uuid.UUID, str, list[uuid.UUID]]]:
        """Active features sharing a ``cluster_signature`` per repo, org-wide.

        Org-wide variant of :meth:`find_duplicate_signatures`. Used by
        :func:`app.scan.audit.audit_scan` to surface drift across every
        tracked repo, not just the ones that ran in the current scan —
        a duplicate seeded by a crashed PR-merge reconcile in repo X
        won't appear in repo X's next scan unless its SHA also changed.

        Returns ``(repo_id, signature, [feature_id, ...])`` triples for
        every PRIMARY-junction repo where one signature has more than
        one active feature. Empty list = healthy.
        """
        stmt = (
            select(
                FeatureToRepo.repo_id,
                Feature.cluster_signature,
                func.array_agg(Feature.id).label("ids"),
            )
            .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
            .where(
                Feature.org_id == self._org_id,
                Feature.is_active.is_(True),
                FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
            )
            .group_by(FeatureToRepo.repo_id, Feature.cluster_signature)
            .having(func.count(Feature.id) > 1)
        )
        result = await self._db.execute(stmt)
        return [(row[0], row[1], list(row[2])) for row in result.all()]

    async def list_current_for_repo(self, repo_id: uuid.UUID) -> list[Feature]:
        """Active rows whose PRIMARY junction points at ``repo_id``."""
        result = await self._db.execute(
            self._scoped(
                select(Feature)
                .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
                .where(
                    Feature.is_active.is_(True),
                    FeatureToRepo.repo_id == repo_id,
                    FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
                )
            ).order_by(Feature.synthesized_at.asc())
        )
        return list(result.scalars().all())

    async def list_current_for_org(self) -> list[Feature]:
        """Snapshot of every active row across the org."""
        result = await self._db.execute(
            self._scoped(select(Feature).where(Feature.is_active.is_(True))).order_by(
                Feature.synthesized_at.asc()
            )
        )
        return list(result.scalars().all())

    async def find_primary_link(self, feature_id: uuid.UUID) -> FeatureToRepo | None:
        """Return the PRIMARY ``feature_to_repo`` row for one feature.

        Powers the narrow PR-merge backend-link refresh, which works one
        feature at a time and needs the PRIMARY junction's
        ``code_locations`` to drive path extraction. Scoped to the
        repo's organisation per the standard ``_scoped`` helper.
        """
        result = await self._db.execute(
            self._scoped(
                select(FeatureToRepo)
                .join(Feature, Feature.id == FeatureToRepo.feature_id)
                .where(
                    FeatureToRepo.feature_id == feature_id,
                    FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
                )
                .limit(1)
            )
        )
        return result.scalar_one_or_none()

    async def list_primary_pairs_for_repo(
        self, repo_id: uuid.UUID
    ) -> list[tuple[Feature, FeatureToRepo]]:
        """``(feature, primary_link)`` pairs for every active row in this repo.

        Used by the ``backend_link`` stage which needs both the feature
        row AND its PRIMARY junction's ``code_locations`` to drive the
        per-feature path extraction. Inactive features are skipped.
        """
        result = await self._db.execute(
            self._scoped(
                select(Feature, FeatureToRepo)
                .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
                .where(
                    Feature.is_active.is_(True),
                    FeatureToRepo.repo_id == repo_id,
                    FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
                )
            )
        )
        return [(row[0], row[1]) for row in result.all()]

    async def cluster_names_for_repo(self, repo_id: uuid.UUID) -> set[str]:
        """Flat set of cluster names already synthesised under this repo.

        Powers the synthesis queue self-heal: diff the cluster list
        against this set to get the pending subset Claude still needs
        to process. PRIMARY-junction-scoped, active-only.
        """
        result = await self._db.execute(
            self._scoped(
                select(Feature.cluster_names)
                .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
                .where(
                    Feature.is_active.is_(True),
                    FeatureToRepo.repo_id == repo_id,
                    FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
                )
            )
        )
        names: set[str] = set()
        for (row_names,) in result.all():
            if row_names:
                names.update(row_names)
        return names
