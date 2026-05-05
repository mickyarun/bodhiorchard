# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Single end-of-pipeline audit — the place anomalies are *detected*.

Phases that run during a scan already raise typed exceptions for the
failure modes they own:

- ``feature_synthesis`` reconciles each repo's batch; the reconciler's
  per-step structured logs cover correctness inside one repo.
- The per-repo skill-extraction body raises ``UnmatchedAuthorsError``
  when ``auto_create_members=false`` and the git log has authors not
  in the user table.

Those guards stay in place — they're load-bearing bug fixes from earlier
stages of the stabilisation plan. This module adds **additional** audits
the in-phase guards can't see: cross-phase consistency checks that need
the full picture once every phase has committed.

The flagship example is the "Bug A early-warning":
    Code indexer found N>0 clusters for a repo, but zero active
    ``features`` rows landed for it. Either (a) Claude rationally
    skipped every cluster as infrastructure (legitimate) or (b)
    something silently swallowed the synthesis output. The in-phase
    audits can't tell these apart at synthesis time; end-of-pipeline
    can, by checking against the code_index payload.

The orphan-feature audit is the integrity gate under incremental CRUD:
every active feature must own exactly one PRIMARY ``feature_to_repo``
junction row. A crashed reconcile or a race could drop one; this
sweep surfaces offenders so an admin tool can soft-delete them.

The audit is **read-only**. The orchestrator decides what to do with
the report — log a warning, raise a typed exception, surface to the
timeline. That separation lets the same audit serve a healthcheck
endpoint or an admin "recheck this scan" button without re-running
phases.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan_phase import ScanPhase
from app.repositories.feature import FeatureRepository
from app.repositories.scan_phase_checkpoint import ScanPhaseCheckpointRepository
from app.scan.context import ScanContext
from app.scan.session import with_session

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RepoAnomaly:
    """One repo's mismatch between clusters and synthesized features.

    A high cluster_count / zero synth_count gap is the signal that
    Bug A (parallel-session sharing) used to produce silently. With
    Bug A fixed, this dataclass remains as a regression guard.
    """

    repo_id: uuid.UUID
    repo_name: str
    cluster_count: int
    synth_count: int


@dataclass(frozen=True)
class DuplicateSignatureFinding:
    """One ``(repo_id, cluster_signature)`` pair owning multiple active features.

    Indicates a crashed reconcile or race between the synthesise stage
    and a PR-merge job: the reconciler matches signature-first and
    UPDATEs in place, so a duplicate active row on the same signature
    means the inactivation step never landed.
    """

    repo_id: uuid.UUID
    cluster_signature: str
    feature_ids: list[uuid.UUID]


@dataclass(frozen=True)
class ScanAuditReport:
    """Snapshot of cross-phase anomalies the orchestrator can act on.

    Empty lists mean clean — the happy path returns a report with every
    field at its default. Each list represents a distinct anomaly class
    so the orchestrator can apply different policies (warn vs. raise).
    """

    missing_repo_synth: list[RepoAnomaly] = field(default_factory=list)
    orphan_features: list[uuid.UUID] = field(default_factory=list)
    duplicate_signatures: list[DuplicateSignatureFinding] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """True when no anomaly category surfaced anything."""
        return (
            not self.missing_repo_synth
            and not self.orphan_features
            and not self.duplicate_signatures
        )


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
        duplicates = await _find_duplicate_signatures(session, ctx)

    report = ScanAuditReport(
        missing_repo_synth=missing,
        orphan_features=orphans,
        duplicate_signatures=duplicates,
    )
    if report.is_clean:
        logger.info("scan_audit_clean", scan_id=str(ctx.scan_id))
    else:
        logger.warning(
            "scan_audit_anomalies",
            scan_id=str(ctx.scan_id),
            missing_repo_synth=len(missing),
            orphan_features=len(orphans),
            duplicate_signatures=len(duplicates),
        )
    return report


async def _find_repos_with_clusters_but_no_synth(
    session: AsyncSession,
    ctx: ScanContext,
) -> list[RepoAnomaly]:
    """Detect Bug-A-class silent failures.

    Joins ``scan_phase_checkpoints[code_index].payload->>'feature_count'``
    against the per-repo synth count. Any repo whose code indexer reported
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
    synth_repo = FeatureRepository(session, org_id=ctx.org_id)
    synth_by_repo = await synth_repo.count_active_per_repo()

    # cluster counts for this scan, joined to the active repo.
    # The ``feature_count`` payload key is set by ``_run_code_index``
    # in scan_repo_loop.py — staying in sync with that contract.
    checkpoint_repo = ScanPhaseCheckpointRepository(session, org_id=ctx.org_id)
    cluster_rows = await checkpoint_repo.list_active_repo_cluster_counts(
        ctx.scan_id, ScanPhase.CODE_INDEX
    )

    anomalies: list[RepoAnomaly] = []
    for repo_id, repo_name, cluster_count in cluster_rows:
        cluster_count = cluster_count or 0
        if cluster_count <= 0:
            continue
        synth_count = synth_by_repo.get(repo_id, 0)
        if synth_count == 0:
            anomalies.append(
                RepoAnomaly(
                    repo_id=repo_id,
                    repo_name=repo_name,
                    cluster_count=cluster_count,
                    synth_count=0,
                )
            )
    return anomalies


async def _find_orphan_features(
    session: AsyncSession,
    ctx: ScanContext,
) -> list[uuid.UUID]:
    """Active features with no PRIMARY ``feature_to_repo`` row.

    Data-integrity invariant under incremental CRUD: every active
    feature must own exactly one PRIMARY junction. A crashed
    reconcile, a partial transaction commit, or a manual DB edit can
    drop one — this sweep surfaces offenders. Empty list is the
    healthy state.
    """
    return await FeatureRepository(session, org_id=ctx.org_id).find_orphan_active_feature_ids()


async def _find_duplicate_signatures(
    session: AsyncSession,
    ctx: ScanContext,
) -> list[DuplicateSignatureFinding]:
    """Active features sharing a ``cluster_signature`` per repo, org-wide.

    Companion to the orphan-feature check: under incremental CRUD the
    reconciler should keep at most one active feature per
    ``(repo_id, cluster_signature)``. Multiple active rows mean a
    crashed reconcile or a race between the scan path and the PR-merge
    webhook job left the inactivation step unfinished. Empty list is
    the healthy state.
    """
    rows = await FeatureRepository(session, org_id=ctx.org_id).find_duplicate_signatures_for_org()
    return [
        DuplicateSignatureFinding(
            repo_id=repo_id,
            cluster_signature=signature,
            feature_ids=ids,
        )
        for repo_id, signature, ids in rows
    ]
