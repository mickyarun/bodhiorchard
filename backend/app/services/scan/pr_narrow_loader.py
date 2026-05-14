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

"""DB-loader helpers for the PR-merge narrow synthesis handler.

Split out from :mod:`app.services.scan.pr_narrow_synthesis` to keep
the handler module under the project's soft 200-line bar. Three
read-only helpers, all going through repositories (no raw SQL in
service code):

* :func:`load_scoped_communities` — turns the affected ``cluster_cache``
  rows at ``head_sha`` into ``Community`` payloads + their signature
  set for downstream reconcile scoping.
* :func:`load_existing_features_by_sig` — looks up the currently-known
  feature row per affected signature (active or inactive) so the
  prompt can render update-aware context.
* :func:`row_to_community` — converts one ``ClusterCache`` row into the
  ``Community`` shape the narrow prompt builder consumes; threaded the
  cluster's structural ``signature`` into ``meta_community_id`` so the
  prompt's per-cluster lookup key matches the reconciler's.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.models.cluster_cache import ClusterCache
from app.repositories.cluster_cache import ClusterCacheRepository
from app.repositories.feature import FeatureRepository
from app.repositories.feature_reads import FeatureReadRepository
from app.schemas.scan import Community
from app.services.scan.synthesis.narrow_prompt import ExistingFeatureContext


async def load_scoped_communities(
    db: Any,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    head_sha: str,
    cluster_ids: list[str],
) -> tuple[list[Community], set[str]]:
    """Read the affected ``cluster_cache`` rows at head SHA and convert to communities.

    Returns ``(communities, signatures)``. The signatures set drives the
    reconciler's ``candidate_filter`` downstream — only features whose
    ``cluster_signature`` is in this set are eligible to be matched or
    soft-deleted by the narrow pass.
    """
    requested = set(cluster_ids)
    rows = await ClusterCacheRepository(db, org_id=org_id).list_for_repo_sha(
        repo_id=repo_id, head_sha=head_sha
    )
    communities: list[Community] = []
    signatures: set[str] = set()
    for row in rows:
        if row.cluster_id not in requested:
            continue
        if not row.signature:
            continue
        communities.append(row_to_community(row))
        signatures.add(row.signature)
    return communities, signatures


def row_to_community(row: ClusterCache) -> Community:
    """Map one ``ClusterCache`` row to the ``Community`` shape the prompt expects.

    The cluster's structural ``signature`` lands in ``meta_community_id``
    so the prompt's per-cluster lookup key matches what the reconciler
    matches on.
    """
    return Community(
        community_id=row.cluster_id,
        label=row.label,
        heuristic_label=row.heuristic_label,
        symbol_count=row.symbol_count,
        cohesion=row.cohesion,
        files=[str(f) for f in (row.files or []) if isinstance(f, str)],
        source_community_ids=[row.cluster_id],
        meta_community_id=row.signature,
    )


async def load_existing_features_by_sig(
    db: Any,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    signatures: set[str],
) -> dict[str, ExistingFeatureContext]:
    """Look up the existing feature (active or inactive) per affected signature.

    Reuses the reconciler's ``bulk_load_for_reconcile`` (which includes
    inactive rows by default) to identify which signatures are in scope,
    then pulls each full row via ``find_by_signature`` so the prompt can
    render the description + capabilities Claude needs to make an
    update-or-keep decision.

    ``find_by_signature`` is called per matched signature. By design the
    narrow path is only invoked when the affected-cluster count is
    small, so the per-signature round-trip is cheap; bulk-by-signature
    is a worthwhile follow-up if the cap is ever raised.
    """
    if not signatures:
        return {}
    all_candidates = await FeatureReadRepository(db, org_id=org_id).bulk_load_for_reconcile(
        repo_id, include_inactive=True
    )
    feat_repo = FeatureRepository(db, org_id=org_id)
    out: dict[str, ExistingFeatureContext] = {}
    for cand in all_candidates:
        if cand.cluster_signature not in signatures:
            continue
        full = await feat_repo.find_by_signature(repo_id, cand.cluster_signature)
        if full is None:
            continue
        out[cand.cluster_signature] = ExistingFeatureContext(
            feature_title=full.feature_title,
            description=full.description,
            capabilities=list((full.capabilities or {}).get("capabilities", [])),
            source=full.source,
            source_ref=full.source_ref,
            feature_status=full.feature_status,
            is_active=full.is_active,
            deactivated_at_sha=full.deactivated_at_sha,
        )
    return out
