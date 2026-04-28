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
        knowledge_item_id: uuid.UUID | None = None,
    ) -> SynthesizedFeature:
        """Insert one immutable pre-merge feature row.

        Called by MCP ``write_feature_registry`` in the same transaction
        that writes ``knowledge_items`` + ``knowledge_to_repo``. The
        NOT NULL ``repo_id`` means this call fails loudly if the caller
        could not resolve ``repo_name`` to a ``TrackedRepository`` —
        which is by design, the silent-orphan symptom that §18.12
        describes.
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
            code_locations=code_locations,
            knowledge_item_id=knowledge_item_id,
            merge_outcome=None,
            synthesized_at=datetime.now(UTC),
        )
        self._db.add(row)
        await self._db.flush()
        await self._db.refresh(row)
        return row

    async def mark_merge_outcome(
        self,
        synth_feature_id: uuid.UUID,
        outcome: MergeOutcome,
        *,
        merged_into_id: uuid.UUID | None = None,
    ) -> None:
        """Set ``merge_outcome`` (and ``merged_into_id`` when MERGED_INTO).

        Invariant enforced in code: ``merged_into_id`` is non-NULL iff
        ``outcome is MergeOutcome.MERGED_INTO``. The DB accepts either
        combination, so this method is the one place that guards it.
        """
        if outcome is MergeOutcome.MERGED_INTO and merged_into_id is None:
            raise ValueError("merged_into_id is required when outcome is MERGED_INTO")
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

    async def mark_all_superseded(self) -> int:
        """Supersede every current row for this org.

        Called by ``POST /scan/reset`` so a subsequent scan sees an
        empty "current pre-merge view" and rebuilds from clean slate.
        The old rows remain in the table for audit — they're just no
        longer returned by ``list_current_for_*``.
        """
        now = datetime.now(UTC)
        result = await self._db.execute(
            sql_update(SynthesizedFeature)
            .where(
                SynthesizedFeature.org_id == self._org_id,
                SynthesizedFeature.superseded_at.is_(None),
            )
            .values(superseded_at=now)
        )
        return result.rowcount

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

        Powers the B2 queue self-heal: diff the GitNexus cluster list
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
