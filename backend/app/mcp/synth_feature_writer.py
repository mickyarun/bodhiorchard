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

"""MCP-side helper for staging synthesised features for reconciliation.

Called by ``write_feature_registry`` (legacy) and the synthesis
prompt's ``write_synthesis_feature`` MCP tool. Each call appends a
``FeatureWrite`` to the per-repo
:mod:`app.mcp.synthesis_accumulator` buffer; the synthesise scan
stage drains the buffer at end-of-batch and feeds it to
:mod:`app.services.feature_reconciler` which performs ALL database
writes (insert / update / revive / mark inactive).

Why no direct DB write here:

* The reconciler needs the full synthesised set in one pass for its
  layered identity match (signature → Jaccard → cosine).
* Per-call inserts trip the partial unique index
  ``ux_ftr_primary_title`` whenever the LLM emits the same title for
  two different clusters; the reconciler resolves that by structural
  signature instead of failing on the first conflict.

The embedding is still computed here so the reconciler doesn't have
to round-trip through the embedder for every fresh insert.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.synthesis_accumulator import accumulate
from app.models.organization import Organization
from app.services.feature_content import try_embed
from app.services.feature_reconciler import FeatureWrite

logger = structlog.get_logger(__name__)


async def persist_synth_feature(
    *,
    db: AsyncSession,  # noqa: ARG001 — kept for signature stability across writers
    org: Organization,
    repo_id: uuid.UUID,
    feature_title: str,
    description: str,
    capabilities: list[str],
    cluster_names: list[str],
    cluster_signature: str,
    code_locations: dict[str, list[str]] | None,
    tags: list[str] | None = None,
    head_sha: str | None = None,  # noqa: ARG001 — reconciler stamps this
    source_ref: str | None = None,
) -> int:
    """Stage one synthesised feature for end-of-batch reconciliation.

    ``cluster_signature`` is mandatory — it is the reconciler's
    primary identity key. ``db`` is accepted to keep the signature
    aligned with peer writers (some compute embeddings via DB-backed
    services); the actual write happens in the reconciler.

    Returns the new accumulator buffer length so the LLM tool can
    surface "queued N features" telemetry without a DB round-trip.
    """
    embedding = await try_embed(feature_title, description)
    write = FeatureWrite(
        feature_title=feature_title,
        description=description,
        capabilities={"capabilities": list(capabilities)},
        cluster_names=list(cluster_names),
        cluster_signature=cluster_signature,
        code_locations=dict(code_locations or {}),
        embedding=embedding,
        tags=list(tags or []),
        source_ref=source_ref,
    )
    queued = accumulate(str(org.id), str(repo_id), write)
    logger.info(
        "synth_feature_accumulated",
        org_id=str(org.id),
        repo_id=str(repo_id),
        feature_title=feature_title,
        cluster_signature=cluster_signature[:12],
        queued=queued,
    )
    return queued
