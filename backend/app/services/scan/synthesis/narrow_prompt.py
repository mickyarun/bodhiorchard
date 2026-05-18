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

"""Narrow synthesis prompt — PR-merge feature reconcile.

Used by :mod:`app.services.scan.pr_narrow_synthesis` when a PR merge
touches a small set of clusters. Differs from the full-scan synthesis
prompt in two ways:

1. Smaller community payload — only the affected clusters, not the
   full repo's reduced meta-communities.
2. Includes the **currently-known feature for each cluster** (active
   or recently inactivated) so Claude can decide whether the existing
   feature still describes the cluster's reality after the PR. The
   reconciler matches by ``cluster_signature``, so re-emitting an
   unchanged write keeps the row stable; an updated write refreshes
   in place; omitting an emit lets the reconciler soft-delete the row
   with a SHA stamp.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.schemas.scan import Community
from app.services.scan.synthesis.prompt import DEFAULT_FILES_PER_COMMUNITY


@dataclass(frozen=True)
class ExistingFeatureContext:
    """The portion of an existing feature we surface back to Claude.

    Kept deliberately small — we hand Claude the bare minimum it needs
    to decide *did this PR change what this feature does?* without
    blowing the prompt budget.
    """

    feature_title: str
    description: str
    capabilities: list[str]
    source: str | None
    source_ref: str | None
    feature_status: str | None
    is_active: bool
    deactivated_at_sha: str | None


def build_narrow_synthesis_prompt(
    *,
    repo_name: str,
    communities: list[Community],
    existing_by_signature: dict[str, ExistingFeatureContext],
    files_per_community: int = DEFAULT_FILES_PER_COMMUNITY,
    repo_id: str | None = None,
) -> str:
    """Render the narrow synthesis prompt.

    ``existing_by_signature`` maps a cluster's ``signature`` (the same
    SHA-256 used by the reconciler) to the currently-known feature for
    that cluster. Communities without an entry are treated as net-new
    (Claude inserts), and existing features whose signature is in the
    map but Claude doesn't re-emit will be soft-deleted by the
    reconciler downstream.
    """
    payload = _payload_for_narrow(
        communities=communities,
        existing_by_signature=existing_by_signature,
        files_per_community=files_per_community,
    )
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    scan_context = _scan_context_block(repo_id=repo_id)
    return _NARROW_PROMPT_TEMPLATE.format(
        repo_name=repo_name,
        cluster_count=len(payload),
        cluster_payload=payload_json,
        scan_context=scan_context,
    )


def _scan_context_block(*, repo_id: str | None) -> str:
    """Repo-id echo-back preamble; empty when no ``repo_id`` was threaded."""
    if not repo_id:
        return ""
    return (
        "\n## Scan context (pass this back verbatim)\n"
        f"- ``repo_id``: {repo_id}\n"
        "Include this field in **every** ``write_synthesis_feature`` call so "
        "the backend binds each feature to this exact repo. Do not invent "
        "or alter the value.\n"
    )


def _payload_for_narrow(
    *,
    communities: list[Community],
    existing_by_signature: dict[str, ExistingFeatureContext],
    files_per_community: int,
) -> list[dict[str, Any]]:
    """Per-cluster payload mirroring the full-prompt shape + existing-feature block."""
    out: list[dict[str, Any]] = []
    for c in communities:
        cluster_ids = list(c.source_community_ids or [])
        if c.community_id and c.community_id not in cluster_ids:
            cluster_ids = [c.community_id, *cluster_ids]
        signature = c.meta_community_id or ""
        existing = existing_by_signature.get(signature) if signature else None
        entry: dict[str, Any] = {
            "community_id": c.community_id or "",
            "cluster_ids": cluster_ids,
            "label": c.label,
            "symbol_count": c.symbol_count,
            "cohesion": _round_or_none(c.cohesion),
            "files": list(c.files[:files_per_community]),
            "signature": signature,
        }
        if existing is not None:
            entry["existing_feature"] = {
                "title": existing.feature_title,
                "description": existing.description,
                "capabilities": list(existing.capabilities),
                "source": existing.source,
                "source_ref": existing.source_ref,
                "status": existing.feature_status,
                "is_active": existing.is_active,
                "deactivated_at_sha": existing.deactivated_at_sha,
            }
        out.append(entry)
    return out


def _round_or_none(value: float | None) -> float | None:
    """Round cohesion to 3dp for prompt readability; preserve None."""
    return None if value is None else round(value, 3)


_NARROW_PROMPT_TEMPLATE = (
    ('You are reconciling features for repository "{repo_name}" after a PR merge.\n\n')
    + """Only the clusters listed below were affected by this PR (their file
membership changed, they appeared, or they disappeared). For each one,
decide whether the existing feature still describes the cluster's
reality, and emit exactly one ``write_synthesis_feature`` call per
cluster you want to keep active.
{scan_context}
Affected clusters ({cluster_count}, JSON):
{cluster_payload}

## How to read each cluster
- ``cluster_ids`` — pass these back verbatim in ``source_community_ids`` so the
  server can expand ``code_locations`` automatically. (Same shape as the
  full-scan prompt.)
- ``signature`` — the cluster's structural identity (SHA-256 of its member
  node-ID list). The reconciler matches your write to an existing row by
  signature first, so re-emitting an unchanged feature keeps the row stable.
- ``files`` — sample of repo-relative paths in this cluster *after* the
  merge. The recurring path-segment is the strongest signal for the
  feature's domain.
- ``existing_feature`` (when present) — the currently-known feature for
  this cluster. Carries title, description, capabilities, source
  (``scan`` or ``bud``), source_ref (e.g. ``BUD-021``), and status.
  When ``is_active`` is false, the feature was soft-deleted by an
  earlier reconcile pass; re-emitting it reactivates it.

## Decision rules (per cluster)
1. **Unchanged in spirit** — the PR changed file membership but the feature
   still represents the same capability. Re-emit ``write_synthesis_feature``
   with the existing title/description/capabilities so the reconciler
   refreshes ``last_seen_sha`` and keeps the row stable.
2. **Materially changed** — the feature does something different now (new
   capability, renamed domain, etc.). Emit with updated description /
   capabilities. The reconciler matches by signature, so the row is updated
   in place; the existing id, bug links, and BUD references are preserved.
3. **No longer a coherent feature** — the cluster's surviving files are
   logging / config / unrelated bits. DO NOT emit. The reconciler will
   soft-delete the row and stamp the deactivating commit.
4. **No ``existing_feature``** — net-new cluster. Emit a fresh write with
   the standard description / capabilities (3-5 sentence business prose,
   canonical domain noun, etc.).
5. **``existing_feature`` with ``source="bud"``** — DO NOT modify; BUD-
   owned features live alongside scan features and the BUD lifecycle path
   owns their state. Skip these clusters entirely.

## Required write_synthesis_feature fields per emit
- ``name``: human-readable feature title.
- ``description``: 3-5 sentence business description.
- ``source_community_ids``: the ``cluster_ids`` array from the cluster above.
- ``code_locations``: ``{{"backend": [...]}}`` / ``{{"frontend": [...]}}``;
  the server unions with the cluster's files automatically.
- ``repo_name``: "{repo_name}"
- ``repo_id``: from the *Scan context* block above (when provided).

Do not invent clusters not in the list above; do not emit two features
for the same signature; do not emit for BUD-sourced existing features.
"""
)
