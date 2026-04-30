# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""SynthesizedFeature data access repository.

Immutable, append-only feature audit. Writes happen once during
``FEATURE_SYNTHESIS`` (MCP ``write_feature_registry``). Merge only
mutates ``merge_outcome`` and ``merged_into_id``. Supersede marks old
rows with ``superseded_at`` but never hard-deletes them.

See ``BODHIORCHARD-ARCHITECTURE.md §18.12``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_item import KnowledgeItem
from app.models.scan_phase import MergeOutcome
from app.models.synthesized_feature import SynthesizedFeature
from app.repositories.base import BaseRepository


class SynthesizedFeatureRepository(BaseRepository[SynthesizedFeature]):
    """Repository for ``synthesized_features`` rows, org-scoped.

    Organisation scoping is inherited from ``BaseRepository``; every
    read method applies ``org_id`` via ``_scoped``. Callers that need
    cross-org admin access (e.g. the recovery endpoint's lookup by
    synth_id) should use ``get_by_id`` which also enforces scope.
    """

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialise the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries.
        """
        super().__init__(SynthesizedFeature, db, org_id=org_id)

    async def list_for_merge_scan(
        self, scan_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str | None, dict | None, list[str] | None, dict | None]]:
        """Per-scan synth rows surfaced by the merge prompt collector.

        Returns ``(knowledge_item_id, description, capabilities,
        cluster_names, code_locations)`` for non-superseded synth rows
        in the given scan, oldest-first so the collector can let later
        rows overwrite earlier ones for the same KI.
        """
        stmt = self._scoped(
            select(
                SynthesizedFeature.knowledge_item_id,
                SynthesizedFeature.description,
                SynthesizedFeature.capabilities,
                SynthesizedFeature.cluster_names,
                SynthesizedFeature.code_locations,
            )
            .where(
                SynthesizedFeature.scan_id == scan_id,
                SynthesizedFeature.superseded_at.is_(None),
                SynthesizedFeature.knowledge_item_id.is_not(None),
            )
            .order_by(SynthesizedFeature.synthesized_at.asc())
        )
        result = await self._db.execute(stmt)
        return [
            (
                row.knowledge_item_id,
                row.description,
                row.capabilities,
                row.cluster_names,
                row.code_locations,
            )
            for row in result.all()
        ]

    async def list_clusters_for_kis(
        self, knowledge_item_ids: list[uuid.UUID]
    ) -> list[tuple[uuid.UUID, list[str] | None]]:
        """Cluster names from the latest non-superseded synth row per KI.

        Returns ``(knowledge_item_id, cluster_names)`` ordered newest
        first so the caller can deduplicate while preserving recency.
        """
        if not knowledge_item_ids:
            return []
        stmt = self._scoped(
            select(SynthesizedFeature.knowledge_item_id, SynthesizedFeature.cluster_names)
            .where(
                SynthesizedFeature.knowledge_item_id.in_(knowledge_item_ids),
                SynthesizedFeature.superseded_at.is_(None),
            )
            .order_by(SynthesizedFeature.synthesized_at.desc())
        )
        result = await self._db.execute(stmt)
        return [(row.knowledge_item_id, row.cluster_names) for row in result.all()]

    async def count_active_per_repo(self) -> dict[uuid.UUID, int]:
        """Per-repo counts of non-superseded synthesized features for the org.

        Returns:
            Dict ``repo_id -> active synth count``. Repos with zero active
            rows are absent.
        """
        stmt = self._scoped(
            select(
                SynthesizedFeature.repo_id,
                func.count(SynthesizedFeature.id).label("synth_count"),
            )
            .where(SynthesizedFeature.superseded_at.is_(None))
            .group_by(SynthesizedFeature.repo_id)
        )
        result = await self._db.execute(stmt)
        return {row.repo_id: row.synth_count for row in result.all()}

    # --- Writes ---------------------------------------------------------

    async def insert(
        self,
        *,
        scan_id: uuid.UUID,
        repo_id: uuid.UUID,
        feature_title: str,
        description: str,
        capabilities: dict[str, Any],
        cluster_names: list[str],
        code_locations: dict[str, Any],
        tags: list[str] | None = None,
        embedding: list[float] | None = None,
        knowledge_item_id: uuid.UUID | None = None,
    ) -> SynthesizedFeature:
        """Insert one immutable pre-merge feature row.

        Called by MCP ``write_feature_registry`` in the same transaction
        that writes ``knowledge_items`` + ``knowledge_to_repo``. The
        NOT NULL ``repo_id`` means this call fails loudly if the caller
        could not resolve ``repo_name`` to a ``TrackedRepository`` —
        which is by design, the silent-orphan symptom that §18.12
        describes.

        ``embedding`` is computed at synthesis write-time so the merge
        phase can cluster likely-duplicates without re-embedding. NULL
        is acceptable for legacy callers; the merge phase will lazy-fill.
        """
        assert self._org_id is not None, "org_id required for writes"
        row = SynthesizedFeature(
            scan_id=scan_id,
            org_id=self._org_id,
            repo_id=repo_id,
            feature_title=feature_title,
            description=description,
            capabilities=capabilities,
            cluster_names=cluster_names,
            tags=list(tags or []),
            code_locations=code_locations,
            embedding=embedding,
            knowledge_item_id=knowledge_item_id,
            merge_outcome=None,
            synthesized_at=datetime.now(UTC),
        )
        self._db.add(row)
        await self._db.flush()
        await self._db.refresh(row)
        return row

    async def set_embedding(
        self,
        synth_feature_id: uuid.UUID,
        embedding: list[float],
    ) -> None:
        """Lazy-fill ``embedding`` on a synth row that pre-dates the column.

        Used by the merge phase's bulk back-fill pass for legacy rows
        whose ``embedding IS NULL`` because they were inserted before
        the column existed. After one sweep, all rows have embeddings
        cached.
        """
        await self._db.execute(
            sql_update(SynthesizedFeature)
            .where(
                SynthesizedFeature.org_id == self._org_id,
                SynthesizedFeature.id == synth_feature_id,
            )
            .values(embedding=embedding)
        )

    async def mark_merge_outcome(
        self,
        synth_feature_id: uuid.UUID,
        outcome: MergeOutcome,
        *,
        merged_into_id: uuid.UUID | None = None,
    ) -> None:
        """Set ``merge_outcome`` (and optionally ``merged_into_id``).

        Invariant: ``merged_into_id`` MUST be NULL for any outcome other
        than ``MERGED_INTO``. For ``MERGED_INTO`` it MAY be NULL — the
        absorbed-into target is sometimes a pre-synth_features
        ``knowledge_item`` (manually entered, or older than this audit
        table) for which no synth row exists. In that case the
        ``knowledge_item_id`` back-fill is the link to the canonical;
        ``merged_into_id`` simply has no synth ancestor to point at.
        """
        if outcome is not MergeOutcome.MERGED_INTO and merged_into_id is not None:
            raise ValueError(f"merged_into_id must be None for outcome={outcome.value!r}")

        await self._db.execute(
            sql_update(SynthesizedFeature)
            .where(
                SynthesizedFeature.org_id == self._org_id,
                SynthesizedFeature.id == synth_feature_id,
            )
            .values(merge_outcome=outcome, merged_into_id=merged_into_id)
        )

    async def list_active_grouped_by_repo_for_scan(
        self, scan_id: uuid.UUID
    ) -> dict[uuid.UUID, list[SynthesizedFeature]]:
        """Active (non-superseded) features produced in this scan, keyed by repo id.

        Used by the timeline serializer to attach feature lists to the
        FEATURE_SYNTHESIS / FEATURE_MERGE chip popovers. Sorted by title
        within each repo for stable rendering.
        """
        result = await self._db.execute(
            self._scoped(
                select(SynthesizedFeature).where(
                    SynthesizedFeature.scan_id == scan_id,
                    SynthesizedFeature.superseded_at.is_(None),
                )
            ).order_by(SynthesizedFeature.repo_id, SynthesizedFeature.feature_title)
        )
        grouped: dict[uuid.UUID, list[SynthesizedFeature]] = {}
        for row in result.scalars().all():
            grouped.setdefault(row.repo_id, []).append(row)
        return grouped

    async def list_unmerged_for_scan(self, scan_id: uuid.UUID) -> list[SynthesizedFeature]:
        """List current synth rows for this scan still awaiting a merge outcome.

        Filters: ``scan_id == scan_id``, ``superseded_at IS NULL``,
        ``merge_outcome IS NULL``. Used by the per-scan **audit** check
        (``_audit_strict``) to verify every NEW row this scan produced
        was stamped — a per-scan responsibility.

        For merge **processing**, prefer :meth:`list_unmerged_org_wide`:
        the merge phase is a cross-scan dedup operation by design and
        must pick up stragglers from cancelled / partially-completed
        prior scans, not just this scan's rows.
        """
        result = await self._db.execute(
            self._scoped(
                select(SynthesizedFeature).where(
                    SynthesizedFeature.scan_id == scan_id,
                    SynthesizedFeature.superseded_at.is_(None),
                    SynthesizedFeature.merge_outcome.is_(None),
                )
            ).order_by(SynthesizedFeature.synthesized_at.asc())
        )
        return list(result.scalars().all())

    async def list_unmerged_org_wide(self) -> list[SynthesizedFeature]:
        """List every current synth row in the org awaiting a merge outcome.

        The merge phase processes the org's full unmerged set in one pass
        so stragglers from cancelled or partially-completed prior scans
        don't accumulate forever. Filters: ``superseded_at IS NULL``,
        ``merge_outcome IS NULL``.

        Ordered by ``synthesized_at`` ascending so the merge prompt sees
        rows in the order they were produced — older scans first, then
        the current scan's output. This keeps the prompt's NEW section
        stable across re-runs of a scan-test workflow.
        """
        result = await self._db.execute(
            self._scoped(
                select(SynthesizedFeature).where(
                    SynthesizedFeature.superseded_at.is_(None),
                    SynthesizedFeature.merge_outcome.is_(None),
                )
            ).order_by(SynthesizedFeature.synthesized_at.asc())
        )
        return list(result.scalars().all())

    async def back_fill_knowledge_item_id(
        self,
        synth_feature_id: uuid.UUID,
        knowledge_item_id: uuid.UUID,
    ) -> None:
        """Set ``knowledge_item_id`` on a synth row after merge promotes it.

        In the staging-then-merge model, synth rows are inserted during
        B2 with ``knowledge_item_id=NULL``; the merge phase creates the
        canonical KI and back-fills this FK so downstream queries
        (e.g. ``find_current_by_knowledge_item_ids``) keep working.
        """
        await self._db.execute(
            sql_update(SynthesizedFeature)
            .where(
                SynthesizedFeature.org_id == self._org_id,
                SynthesizedFeature.id == synth_feature_id,
            )
            .values(knowledge_item_id=knowledge_item_id)
        )

    async def mark_canonical_for_active_kis(self) -> int:
        """First half of the post-merge audit: NULL outcome + active KI → CANONICAL.

        These rows represent features the merge subprocess saw in its
        prompt and rationally chose not to merge — a unique feature has
        no duplicate, so ``apply_feature_merge_plan`` never absorbs it.
        They are canonical by default; flagging them as ``unvisited``
        (the legacy single-tier audit's behaviour) produced spurious
        ``merge_incomplete`` failures and prevented the SKILL_REMAP
        cascade from running.

        Returns:
            Number of rows flipped (informational; non-zero is healthy).
        """
        result = await self._db.execute(
            sql_update(SynthesizedFeature)
            .where(
                SynthesizedFeature.org_id == self._org_id,
                SynthesizedFeature.superseded_at.is_(None),
                SynthesizedFeature.merge_outcome.is_(None),
                SynthesizedFeature.knowledge_item_id.in_(
                    select(KnowledgeItem.id).where(
                        KnowledgeItem.org_id == self._org_id,
                        KnowledgeItem.is_active.is_(True),
                    )
                ),
            )
            .values(merge_outcome=MergeOutcome.CANONICAL)
        )
        return result.rowcount

    async def mark_unvisited_for_inactive_kis(self) -> int:
        """Second half of the post-merge audit: remaining NULL → UNVISITED.

        After ``mark_canonical_for_active_kis`` runs, the only NULLs
        left are rows whose ``knowledge_item_id`` points at a KI that
        was deactivated (or hard-deleted) without the merge subprocess
        ever recording a ``merged_into`` outcome. That's the genuine
        partial-merge signal — the caller raises ``MergeIncompleteError``
        on a non-zero return so the FAILED checkpoint carries
        ``error_code='merge_incomplete'``.

        Order matters: this method assumes the canonical sweep has
        already run, so any remaining NULL is genuinely orphan.
        """
        result = await self._db.execute(
            sql_update(SynthesizedFeature)
            .where(
                SynthesizedFeature.org_id == self._org_id,
                SynthesizedFeature.superseded_at.is_(None),
                SynthesizedFeature.merge_outcome.is_(None),
            )
            .values(merge_outcome=MergeOutcome.UNVISITED)
        )
        return result.rowcount

    async def supersede_prior_by_title(
        self,
        *,
        repo_id: uuid.UUID,
        feature_title: str,
    ) -> int:
        """Mark older rows for the same (repo, title) as superseded.

        Called when a newer scan writes a fresh row for a feature that
        already has historical rows. Keeps the "current pre-merge view"
        ( ``superseded_at IS NULL`` ) populated with one row per (repo,
        title), without deleting history.
        """
        now = datetime.now(UTC)
        result = await self._db.execute(
            sql_update(SynthesizedFeature)
            .where(
                SynthesizedFeature.org_id == self._org_id,
                SynthesizedFeature.repo_id == repo_id,
                SynthesizedFeature.feature_title == feature_title,
                SynthesizedFeature.superseded_at.is_(None),
            )
            .values(superseded_at=now)
        )
        return result.rowcount

    # --- Reads ----------------------------------------------------------

    async def get_by_id(self, synth_feature_id: uuid.UUID) -> SynthesizedFeature | None:
        """Fetch a single row by primary key within org scope."""
        result = await self._db.execute(
            self._scoped(
                select(SynthesizedFeature).where(
                    SynthesizedFeature.id == synth_feature_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def find_current_by_title(self, feature_title: str) -> list[SynthesizedFeature]:
        """Return all current (non-superseded) rows for one feature title.

        A single feature can have multiple rows when several repos each
        synthesised the same title; all of them share the same merge fate.
        Used by the post-merge audit to mark outcomes in lockstep when
        a single feature was synthesised under multiple repo runs.
        """
        result = await self._db.execute(
            self._scoped(
                select(SynthesizedFeature).where(
                    SynthesizedFeature.feature_title == feature_title,
                    SynthesizedFeature.superseded_at.is_(None),
                )
            ).order_by(SynthesizedFeature.synthesized_at.asc())
        )
        return list(result.scalars().all())

    async def find_current_by_knowledge_item_ids(
        self,
        knowledge_item_ids: list[uuid.UUID],
    ) -> list[SynthesizedFeature]:
        """Return all current rows whose ``knowledge_item_id`` matches one of the inputs.

        Id-keyed counterpart to :meth:`find_current_by_title`. Used by
        ``apply_feature_merge_plan`` so the post-merge audit is stable
        under feature rename or title collision.
        """
        if not knowledge_item_ids:
            return []
        result = await self._db.execute(
            self._scoped(
                select(SynthesizedFeature).where(
                    SynthesizedFeature.knowledge_item_id.in_(knowledge_item_ids),
                    SynthesizedFeature.superseded_at.is_(None),
                )
            ).order_by(SynthesizedFeature.synthesized_at.asc())
        )
        return list(result.scalars().all())

    async def list_current_for_repo(self, repo_id: uuid.UUID) -> list[SynthesizedFeature]:
        """List current (non-superseded) rows for one repo."""
        result = await self._db.execute(
            self._scoped(
                select(SynthesizedFeature).where(
                    SynthesizedFeature.repo_id == repo_id,
                    SynthesizedFeature.superseded_at.is_(None),
                )
            ).order_by(SynthesizedFeature.synthesized_at.asc())
        )
        return list(result.scalars().all())

    async def list_current_for_org(self) -> list[SynthesizedFeature]:
        """Snapshot of all current pre-merge rows across the org.

        Used as the canonical input to ``FEATURE_MERGE`` — the merge
        subprocess sees exactly these titles and decides canonicals.
        """
        result = await self._db.execute(
            self._scoped(
                select(SynthesizedFeature).where(
                    SynthesizedFeature.superseded_at.is_(None),
                )
            ).order_by(
                SynthesizedFeature.repo_id.asc(),
                SynthesizedFeature.synthesized_at.asc(),
            )
        )
        return list(result.scalars().all())

    async def cluster_names_for_repo(self, repo_id: uuid.UUID) -> set[str]:
        """Return the flat set of cluster names already synthesised for a repo.

        Powers the B2 queue self-heal: diff the cluster list
        against this set to get the pending subset that Claude still
        needs to process.
        """
        result = await self._db.execute(
            self._scoped(
                select(SynthesizedFeature.cluster_names).where(
                    SynthesizedFeature.repo_id == repo_id,
                    SynthesizedFeature.superseded_at.is_(None),
                )
            )
        )
        names: set[str] = set()
        for (row_names,) in result.all():
            if row_names:
                names.update(row_names)
        return names

    async def list_unvisited_for_scan(self, scan_id: uuid.UUID) -> list[SynthesizedFeature]:
        """List rows flagged UNVISITED by the post-merge audit for this scan.

        Retry paths feed this list back into the next ``FEATURE_MERGE``
        invocation so Claude only reconsiders what it missed.
        """
        result = await self._db.execute(
            self._scoped(
                select(SynthesizedFeature).where(
                    SynthesizedFeature.scan_id == scan_id,
                    SynthesizedFeature.merge_outcome == MergeOutcome.UNVISITED,
                )
            ).order_by(SynthesizedFeature.feature_title.asc())
        )
        return list(result.scalars().all())

    async def list_merged_into(self, canonical_id: uuid.UUID) -> list[SynthesizedFeature]:
        """List rows that were consolidated into ``canonical_id`` during merge.

        Used by the bad-merge recovery endpoint to show the admin which
        features are hidden under a surviving canonical.
        """
        result = await self._db.execute(
            self._scoped(
                select(SynthesizedFeature).where(
                    SynthesizedFeature.merged_into_id == canonical_id,
                    SynthesizedFeature.merge_outcome == MergeOutcome.MERGED_INTO,
                )
            ).order_by(SynthesizedFeature.synthesized_at.asc())
        )
        return list(result.scalars().all())
