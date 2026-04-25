# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Single end-of-pipeline audit — the place anomalies are *detected*.

Phases that run during a scan already raise typed exceptions for the
failure modes they own:

- ``feature_synthesis`` raises ``OrphanFeaturesError`` when
  ``verify_repo_links`` finds knowledge_items missing a repo link.
- ``feature_merge`` raises ``MergeIncompleteError`` when synth rows
  with inactive KIs survived the canonical pass.
- The per-repo skill-extraction body raises ``UnmatchedAuthorsError``
  when ``auto_create_members=false`` and the git log has authors not
  in the user table.

Those guards stay in place — they're load-bearing bug fixes from earlier
stages of the stabilisation plan. This module adds **additional** audits
the in-phase guards can't see: cross-phase consistency checks that need
the full picture once every phase has committed.

The flagship example is the "Bug A early-warning":
    GitNexus indexed N>0 clusters for a repo, but zero
    synthesized_features rows landed for it. Either (a) Claude rationally
    skipped every cluster as infrastructure (legitimate) or (b) something
    silently swallowed the synthesis output (the parallel-session bug).
    The in-phase audits can't tell these apart at synthesis time;
    end-of-pipeline can, by checking against the gitnexus_index payload.

The audit is **read-only**. The orchestrator decides what to do with the
report — log a warning, raise a typed exception, surface to the timeline.
That separation lets the same audit serve a healthcheck endpoint or an
admin "recheck this scan" button without re-running phases.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import structlog
from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_item import KnowledgeItem, KnowledgeRepoLink
from app.models.scan_phase import ScanPhase
from app.models.scan_phase_checkpoint import ScanPhaseCheckpoint
from app.models.synthesized_feature import SynthesizedFeature
from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.scan.context import ScanContext
from app.scan.session import with_session

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RepoAnomaly:
    """One repo's mismatch between gitnexus clusters and synthesized features.

    A high cluster_count / zero synth_count gap is the signal that
    Bug A (parallel-session sharing) used to produce silently. With
    Bug A fixed, this dataclass remains as a regression guard.
    """

    repo_id: uuid.UUID
    repo_name: str
    cluster_count: int
    synth_count: int


@dataclass(frozen=True)
class ScanAuditReport:
    """Snapshot of cross-phase anomalies the orchestrator can act on.

    Empty lists mean clean — the happy path returns a report with every
    field at its default. Each list represents a distinct anomaly class
    so the orchestrator can apply different policies (warn vs. raise).
    """

    missing_repo_synth: list[RepoAnomaly] = field(default_factory=list)
    orphan_features: list[uuid.UUID] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """True when no anomaly category surfaced anything."""
        return not self.missing_repo_synth and not self.orphan_features


async def audit_scan(ctx: ScanContext) -> ScanAuditReport:
    """Single-pass audit reading from committed checkpoints + DB.

    Runs after ``persist_results`` so every phase's writes are durable.
    Opens its own session via ``with_session`` — the audit is independent
    of the pipeline's transaction and can be re-invoked from a recovery
    endpoint without re-running phases.

    Args:
        ctx: Scan context. Only ``scan_id`` and ``org_id`` are used;
            per-repo fields are ignored (this is a global audit).

    Returns:
        ``ScanAuditReport`` describing any anomalies. Caller decides how
        to surface them (log, raise, push to UI).
    """
    async with with_session(ctx.org_id) as session:
        missing = await _find_repos_with_clusters_but_no_synth(session, ctx)
        orphans = await _find_orphan_features(session, ctx)

    report = ScanAuditReport(
        missing_repo_synth=missing,
        orphan_features=orphans,
    )
    if report.is_clean:
        logger.info("scan_audit_clean", scan_id=str(ctx.scan_id))
    else:
        logger.warning(
            "scan_audit_anomalies",
            scan_id=str(ctx.scan_id),
            missing_repo_synth=len(missing),
            orphan_features=len(orphans),
        )
    return report


async def _find_repos_with_clusters_but_no_synth(
    session: AsyncSession,
    ctx: ScanContext,
) -> list[RepoAnomaly]:
    """Detect Bug-A-class silent failures.

    Joins ``scan_phase_checkpoints[gitnexus_index].payload->>'feature_count'``
    against the per-repo synth count. Any repo whose gitnexus reported
    clusters but produced zero ``synthesized_features`` rows is flagged.

    Returning empty here is the healthy state. A non-empty list means
    one of:
      - Claude rationally skipped every cluster as infrastructure
        (legitimate; the orchestrator should warn-only).
      - Synthesis was silently dropped (the regression path Bug A
        produced; the orchestrator should warn loudly).

    The audit can't distinguish those — distinguishing requires
    inspecting Claude's output and is best left to a human reviewer
    looking at the timeline. The audit's job is "this is unusual",
    not "this is wrong".
    """
    # Per-repo synth counts in one query.
    synth_counts_stmt = (
        select(
            SynthesizedFeature.repo_id,
            func.count(SynthesizedFeature.id).label("synth_count"),
        )
        .where(
            SynthesizedFeature.org_id == ctx.org_id,
            SynthesizedFeature.superseded_at.is_(None),
        )
        .group_by(SynthesizedFeature.repo_id)
    )
    synth_rows = (await session.execute(synth_counts_stmt)).all()
    synth_by_repo = {row.repo_id: row.synth_count for row in synth_rows}

    # GitNexus cluster counts for this scan, joined to the active repo.
    # The ``feature_count`` payload key is set by ``_run_gitnexus_index``
    # in scan_repo_loop.py — staying in sync with that contract.
    cluster_stmt = (
        select(
            ScanPhaseCheckpoint.repo_id,
            TrackedRepository.name,
            ScanPhaseCheckpoint.payload["feature_count"]
            .astext.cast(Integer)
            .label("cluster_count"),
        )
        .join(
            TrackedRepository,
            TrackedRepository.id == ScanPhaseCheckpoint.repo_id,
        )
        .where(
            ScanPhaseCheckpoint.scan_id == ctx.scan_id,
            ScanPhaseCheckpoint.phase == ScanPhase.GITNEXUS_INDEX,
            ScanPhaseCheckpoint.org_id == ctx.org_id,
            TrackedRepository.status == RepoStatus.ACTIVE,
        )
    )
    cluster_rows = (await session.execute(cluster_stmt)).all()

    anomalies: list[RepoAnomaly] = []
    for row in cluster_rows:
        cluster_count = row.cluster_count or 0
        if cluster_count <= 0:
            continue
        synth_count = synth_by_repo.get(row.repo_id, 0)
        if synth_count == 0:
            anomalies.append(
                RepoAnomaly(
                    repo_id=row.repo_id,
                    repo_name=row.name,
                    cluster_count=cluster_count,
                    synth_count=0,
                )
            )
    return anomalies


async def _find_orphan_features(
    session: AsyncSession,
    ctx: ScanContext,
) -> list[uuid.UUID]:
    """Active feature_registry KIs with no ``knowledge_to_repo`` link.

    The per-repo ``verify_repo_links`` audit already auto-repairs and
    raises on unfixable orphans during synthesis. This is the
    end-of-pipeline check against drift introduced after synthesis —
    e.g. a merge that consolidated two features and accidentally
    detached their links. Empty list is the healthy state.
    """
    stmt = (
        select(KnowledgeItem.id)
        .outerjoin(
            KnowledgeRepoLink,
            KnowledgeRepoLink.knowledge_id == KnowledgeItem.id,
        )
        .where(
            KnowledgeItem.org_id == ctx.org_id,
            KnowledgeItem.category == "feature_registry",
            KnowledgeItem.is_active.is_(True),
            KnowledgeRepoLink.repo_id.is_(None),
        )
    )
    result = await session.execute(stmt)
    return [row.id for row in result.all()]
