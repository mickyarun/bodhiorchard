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

"""Reconcile a synthesised feature batch against the existing active set.

The sole incremental writer for ``features`` + ``feature_to_repo`` under
the new lifecycle. Currently called from
``services/scan/stages/synthesize.py`` at the end of each per-repo
synthesis pass; the planned PR-merge webhook job will reuse the same
entrypoint.

The reconciler matches each synthesised entry to an existing row via a
layered identity strategy (cluster_signature → Jaccard ≥ 0.7 →
embedding cosine ≥ 0.85), then UPDATEs / REVIVEs / INSERTs accordingly.
Existing active rows that nothing matched are flipped ``is_active=False``
so removed features are preserved (and revivable on re-introduction)
rather than silently disappearing.

Logging at every fork (``match_via=signature|jaccard|cosine|insert``,
plus the chosen score) drives the threshold-tuning loop documented in
the plan.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature_match_log import FeatureMatchLog
from app.repositories.feature import FeatureRepository
from app.repositories.feature_reads import FeatureReadRepository, ReconcilerCandidate
from app.repositories.feature_to_repo import upsert_primary

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FeatureWrite:
    """One synthesised feature ready for reconciliation."""

    feature_title: str
    description: str
    capabilities: dict[str, Any]
    cluster_names: list[str]
    cluster_signature: str
    code_locations: dict[str, list[str]] | None
    embedding: list[float] | None
    tags: list[str]
    feature_status: str | None = None
    source_ref: str | None = None


@dataclass
class ReconcileResult:
    """Summary of one reconcile pass."""

    inserted: int = 0
    updated: int = 0
    revived: int = 0
    inactivated: int = 0
    matches_by_strategy: dict[str, int] = field(default_factory=dict)
    match_log_rows: list[FeatureMatchLog] = field(default_factory=list)


# Default thresholds — keep aligned with the plan. Override at call site
# when running tuning experiments.
JACCARD_THRESHOLD = 0.7
COSINE_THRESHOLD = 0.85


async def reconcile_features_for_repo(
    *,
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    head_sha: str,
    synthesised: list[FeatureWrite],
    jaccard_threshold: float = JACCARD_THRESHOLD,
    cosine_threshold: float = COSINE_THRESHOLD,
    candidate_filter: Callable[[ReconcilerCandidate], bool] | None = None,
) -> ReconcileResult:
    """Apply ``synthesised`` to ``repo_id`` via incremental CRUD.

    Steps:

    1. Bulk-load every existing feature for ``repo_id`` (active +
       inactive) so revival is single-pass.
    2. For each ``FeatureWrite``, run :func:`_match_strategy` to pick
       an existing row by signature → Jaccard → cosine. First hit
       wins; ties broken by score.
    3. If matched: revive (when inactive) + ``update_in_place`` + refresh
       PRIMARY junction. If not: ``insert`` + create PRIMARY junction.
    4. Mark every active row that nothing matched as inactive.

    ``candidate_filter`` (optional) narrows BOTH the matching pool and
    the inactivation pool to a subset of the loaded candidates. The
    full-scan caller leaves it ``None`` (default behaviour preserved);
    the PR-merge narrow-synthesis caller passes a predicate that admits
    only features whose ``cluster_signature`` is in the affected
    signatures set — so features outside the scope are immune from
    soft-delete even if they don't appear in ``synthesised``.

    Returns counts so the caller can surface "+5 added, 2 revived,
    1 removed" telemetry.
    """
    reads = FeatureReadRepository(db, org_id=org_id)
    all_candidates = await reads.bulk_load_for_reconcile(repo_id, include_inactive=True)
    candidates = (
        [c for c in all_candidates if candidate_filter(c)]
        if candidate_filter is not None
        else all_candidates
    )
    by_signature: dict[str, ReconcilerCandidate] = {c.cluster_signature: c for c in candidates}
    matched_ids: set[uuid.UUID] = set()
    feat_repo = FeatureRepository(db, org_id=org_id)
    result = ReconcileResult()

    for write in synthesised:
        match, match_via, score = _match_strategy(
            write,
            candidates,
            by_signature,
            matched_ids,
            jaccard_threshold=jaccard_threshold,
            cosine_threshold=cosine_threshold,
        )
        decision: str
        if match is None:
            await _insert_new(
                feat_repo,
                db=db,
                repo_id=repo_id,
                head_sha=head_sha,
                write=write,
            )
            result.inserted += 1
            decision = "inserted"
        else:
            matched_ids.add(match.feature_id)
            was_inactive = not match.is_active
            if was_inactive:
                await feat_repo.revive(match.feature_id, last_seen_sha=head_sha)
                result.revived += 1
            await _update_existing(
                feat_repo,
                db=db,
                feature_id=match.feature_id,
                repo_id=repo_id,
                head_sha=head_sha,
                write=write,
            )
            result.updated += 1
            decision = "revived" if was_inactive else "updated"
        result.matches_by_strategy[match_via] = result.matches_by_strategy.get(match_via, 0) + 1
        result.match_log_rows.append(
            FeatureMatchLog(
                org_id=org_id,
                repo_id=repo_id,
                head_sha=head_sha,
                match_via=match_via,
                score=round(score, 4),
                feature_title=write.feature_title[:500],
                matched_feature_id=match.feature_id if match else None,
                decision=decision,
            )
        )
        logger.info(
            "reconcile_match",
            org_id=str(org_id),
            repo_id=str(repo_id),
            head_sha=head_sha[:8] if head_sha else "",
            match_via=match_via,
            score=round(score, 4),
            feature_title=write.feature_title,
            matched_id=str(match.feature_id) if match else None,
            decision=decision,
        )

    unmatched_active = [
        c.feature_id for c in candidates if c.is_active and c.feature_id not in matched_ids
    ]
    if unmatched_active:
        result.inactivated = await feat_repo.mark_inactive(unmatched_active, head_sha=head_sha)
    logger.info(
        "reconcile_done",
        org_id=str(org_id),
        repo_id=str(repo_id),
        head_sha=head_sha[:8] if head_sha else "",
        inserted=result.inserted,
        updated=result.updated,
        revived=result.revived,
        inactivated=result.inactivated,
    )
    return result


async def _insert_new(
    feat_repo: FeatureRepository,
    *,
    db: AsyncSession,
    repo_id: uuid.UUID,
    head_sha: str,
    write: FeatureWrite,
) -> None:
    """Insert a new feature row + PRIMARY junction in one transaction.

    Stamps both ``last_seen_sha`` and ``created_at_sha`` to ``head_sha``
    so the row carries its birth SHA forward. ``created_at_sha`` never
    changes after this; ``last_seen_sha`` advances on every reconcile
    that re-confirms the feature. The Features API joins both against
    ``pull_requests.merge_commit_sha`` to surface "Created by PR #N"
    and "Last touched by PR #M" on the card.
    """
    feature = await feat_repo.insert(
        feature_title=write.feature_title,
        description=write.description,
        capabilities=write.capabilities,
        cluster_names=list(write.cluster_names),
        cluster_signature=write.cluster_signature,
        tags=list(write.tags),
        embedding=write.embedding,
        source="scan",
        source_ref=write.source_ref,
        feature_status=write.feature_status,
        last_seen_sha=head_sha,
        created_at_sha=head_sha,
    )
    await upsert_primary(
        db,
        feature_id=feature.id,
        repo_id=repo_id,
        feature_title=write.feature_title,
        code_locations=dict(write.code_locations or {}),
    )


async def _update_existing(
    feat_repo: FeatureRepository,
    *,
    db: AsyncSession,
    feature_id: uuid.UUID,
    repo_id: uuid.UUID,
    head_sha: str,
    write: FeatureWrite,
) -> None:
    """Refresh feature fields + PRIMARY junction code_locations."""
    # Latest write's cluster_names wins; surfaces during threshold tuning
    # if it masks missed clusters.
    await feat_repo.update_in_place(
        feature_id,
        feature_title=write.feature_title,
        description=write.description,
        capabilities=write.capabilities,
        cluster_names=list(write.cluster_names),
        cluster_signature=write.cluster_signature,
        tags=list(write.tags),
        embedding=write.embedding,
        last_seen_sha=head_sha,
        feature_status=write.feature_status,
    )
    await upsert_primary(
        db,
        feature_id=feature_id,
        repo_id=repo_id,
        feature_title=write.feature_title,
        code_locations=dict(write.code_locations or {}),
    )


# O(n*m) — fine at hundreds; revisit at 5k+ features per repo.
def _match_strategy(
    write: FeatureWrite,
    candidates: list[ReconcilerCandidate],
    by_signature: dict[str, ReconcilerCandidate],
    matched_ids: set[uuid.UUID],
    *,
    jaccard_threshold: float,
    cosine_threshold: float,
) -> tuple[ReconcilerCandidate | None, str, float]:
    """Layered identity matcher: signature → Jaccard → cosine.

    Returns ``(candidate, match_via, score)`` where ``match_via`` is
    one of ``signature``, ``jaccard``, ``cosine``, ``insert``. Score
    is 1.0 for an exact signature match, the Jaccard / cosine value
    for the fallback tiers, and 0.0 for ``insert``.

    Skips candidates already claimed by a prior synthesised entry
    (``matched_ids``) so two synthesised features cannot collapse onto
    the same existing row.
    """
    sig_match = by_signature.get(write.cluster_signature)
    if sig_match is not None and sig_match.feature_id not in matched_ids:
        return sig_match, "signature", 1.0

    write_paths = _flatten_paths(write.code_locations)
    if write_paths:
        best_jac: tuple[ReconcilerCandidate, float] | None = None
        for cand in candidates:
            if cand.feature_id in matched_ids:
                continue
            cand_paths = _flatten_paths(cand.code_locations)
            if not cand_paths:
                continue
            score = _jaccard(write_paths, cand_paths)
            if score >= jaccard_threshold and (best_jac is None or score > best_jac[1]):
                best_jac = (cand, score)
        if best_jac is not None:
            return best_jac[0], "jaccard", best_jac[1]

    if write.embedding:
        best_cos: tuple[ReconcilerCandidate, float] | None = None
        for cand in candidates:
            if cand.feature_id in matched_ids or cand.embedding is None:
                continue
            score = _cosine(write.embedding, cand.embedding)
            if score >= cosine_threshold and (best_cos is None or score > best_cos[1]):
                best_cos = (cand, score)
        if best_cos is not None:
            return best_cos[0], "cosine", best_cos[1]

    return None, "insert", 0.0


def _flatten_paths(locations: dict[str, list[str]] | None) -> set[str]:
    """Flatten ``{frontend: [...], backend: [...]}`` into a set of paths."""
    if not locations:
        return set()
    out: set[str] = set()
    for value in locations.values():
        if isinstance(value, list):
            out.update(p for p in value if isinstance(p, str))
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity ``|a ∩ b| / |a ∪ b|``. Returns 0 for empty input."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity ``a·b / (|a|·|b|)``. Returns 0 on length mismatch."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
